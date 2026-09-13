"""CustomTkinter desktop app: NSE Data Fetcher.

A single-window form (per docs/DESIGN.md §11) that lets a non-technical user
add stocks/indices/lists, pick an interval and date range, and download
everything into one Excel workbook.

Built on customtkinter (a themed wrapper around Tkinter) for a modern,
dark-mode-aware look. customtkinter has no listbox or date-picker widget of
its own, so the suggestions/selection lists stay plain tk.Listbox (styled to
match the CTk theme's colors) and the date fields stay tkcalendar's
DateEntry -- both mixed into an otherwise CTk-styled window, which is the
normal way CTk apps cover gaps in its widget set.
"""

from __future__ import annotations

import logging
import re
import threading
import tkinter as tk
from datetime import date, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from tkcalendar import DateEntry

import applog
import settings
from downloader import Entry, download_all, entry_from_symbol, validate_date_range
from importer import parse_file, parse_pasted_text
from lists import ListNotFoundError, ListResolver, WorkbookLockedError
from symbols import SymbolNotFoundError, SymbolResolver

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

ICON_PATH = Path(__file__).parent / "assets" / "icon.png"
# Kept as a real Markdown file rather than a string baked into this module
# so it's easy for a developer to read/diff on its own -- update it
# whenever the behavior it describes (interval limits, error messages,
# settings, etc.) changes.
HELP_PATH = Path(__file__).parent / "HELP.md"

INTERVAL_CHOICES = [("5 min", "5min"), ("15 min", "15min"), ("1 hour", "1hour"), ("Daily", "daily")]


def _theme_color(pair: tuple[str, str]) -> str:
    """Pick the (light, dark) value from a CTk theme color pair for the current appearance mode.

    Plain tk widgets (the listboxes below) don't auto-adapt to light/dark
    like CTk widgets do, so their colors are resolved once, up front, from
    the same theme CTk itself is using -- keeping them visually consistent
    with the rest of the window even though they're not CTk widgets.
    """
    return pair[0] if ctk.get_appearance_mode() == "Light" else pair[1]


def _fix_dateentry_dropdown_closing(date_entry: DateEntry) -> None:
    """Work around two CustomTkinter/tkcalendar focus conflicts that closed or froze the calendar.

    1. CTk.__init__ installs `self.bind_all("<Button-1>", ...)` (to let
       clicking outside a CTkEntry remove its focus highlight), which calls
       `event.widget.focus_set()` for every left-click app-wide. When the
       click is on DateEntry's own drop-down arrow, that fires *after*
       tkcalendar's own handler has opened the calendar and focused it,
       immediately stealing focus back to the DateEntry -- so the
       calendar's <FocusOut> handler withdraws it in the same click, before
       it's ever visibly open. Fixed by binding an extra <ButtonPress-1>
       handler on the DateEntry that returns "break", stopping the event
       from reaching bind_all's "all" bindtag (tkcalendar's own handler is
       bound first, so it still runs before this).

    2. Separately, clicking the calendar's own month/year "<"/">" nav
       buttons closes it too, unrelated to CTk: ttk.Button's default click
       handling calls focus_set() on itself, which moves focus away from
       the calendar frame tkcalendar expects to hold it, so its <FocusOut>
       handler withdraws the popup -- even though the month/year *does*
       change underneath. Fixed by intercepting each nav button's own
       <ButtonPress-1> at the widget-instance bindtag (which runs before
       the button's class bindtag, where the default focus-taking click
       handling lives) to invoke it manually and return "break", skipping
       the class handler -- and the focus-taking -- entirely.
    """
    date_entry.bind("<ButtonPress-1>", lambda _event: "break", add="+")

    def intercept_click(button):
        """Invoke `button`'s command directly, then block its default (focus-taking) click handling."""

        def handler(_event):
            button.after_idle(button.invoke)
            return "break"

        button.bind("<ButtonPress-1>", handler)

    calendar = date_entry._calendar
    for nav_button_name in ("_l_month", "_r_month", "_l_year", "_r_year"):
        intercept_click(getattr(calendar, nav_button_name))


def _styled_listbox(parent, **kwargs) -> tk.Listbox:
    """Create a tk.Listbox colored to match the current CTk theme."""
    entry_theme = ctk.ThemeManager.theme["CTkEntry"]
    button_theme = ctk.ThemeManager.theme["CTkButton"]
    return tk.Listbox(
        parent,
        bg=_theme_color(entry_theme["fg_color"]),
        fg=_theme_color(entry_theme["text_color"]),
        selectbackground=_theme_color(button_theme["fg_color"]),
        selectforeground=_theme_color(button_theme["text_color"]),
        highlightthickness=1,
        highlightbackground=_theme_color(entry_theme["border_color"]),
        highlightcolor=_theme_color(entry_theme["border_color"]),
        relief="flat",
        borderwidth=0,
        **kwargs,
    )


_BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")


def _insert_markdown(textbox: ctk.CTkTextbox, markdown_text: str) -> None:
    """Insert `markdown_text` into `textbox` with minimal Markdown rendering.

    Only handles the small subset HELP.md actually uses -- '#'/'##'
    headings and **bold** spans -- rather than pulling in a full Markdown
    parser dependency for one help dialog. Anything else (table syntax,
    links, etc.) is inserted as plain text.
    """
    # CTkTextbox.tag_config refuses a "font" option ("incompatible with
    # scaling"); its underlying real tkinter.Text widget doesn't have that
    # restriction, so tags are configured there directly instead.
    real_textbox = textbox._textbox
    real_textbox.tag_config("h1", font=ctk.CTkFont(size=18, weight="bold"))
    real_textbox.tag_config("h2", font=ctk.CTkFont(size=15, weight="bold"))
    real_textbox.tag_config("bold", font=ctk.CTkFont(size=13, weight="bold"))

    for line in markdown_text.splitlines():
        if line.startswith("## "):
            textbox.insert("end", line[3:] + "\n", "h2")
            continue
        if line.startswith("# "):
            textbox.insert("end", line[2:] + "\n", "h1")
            continue
        if line.startswith("- "):
            line = "  • " + line[2:]

        position = 0
        for match in _BOLD_PATTERN.finditer(line):
            textbox.insert("end", line[position : match.start()])
            textbox.insert("end", match.group(1), "bold")
            position = match.end()
        textbox.insert("end", line[position:] + "\n")


class App(ctk.CTk):
    """The application's single top-level window."""

    def __init__(self):
        """Build all widgets and load the symbol/list resolvers."""
        super().__init__()
        self.title("NSE Data Fetcher")
        try:
            self.iconphoto(True, tk.PhotoImage(file=str(ICON_PATH)))
        except tk.TclError:
            logger.warning("Couldn't load app icon from %s", ICON_PATH, exc_info=True)

        # customtkinter widgets scale their own font/DPI automatically, but
        # the plain tk/ttk widgets mixed in below (Listbox, DateEntry) don't
        # participate in that at all -- they're left at Tk's tiny system
        # default, which reads fine on macOS but renders visibly smaller
        # than the rest of the UI on Windows. A CTkFont applied explicitly
        # to them tracks the same scaling CTk's own widgets use.
        self._widget_font = ctk.CTkFont(size=13)

        self.symbol_resolver = SymbolResolver()
        self.list_resolver = ListResolver()
        self.entries: list[Entry] = []
        # Set right before an arrow-key press programmatically changes the
        # suggestions listbox's selection, so _on_suggestion_selected (bound
        # to <<ListboxSelect>>, which fires for that too) knows not to treat
        # it as a commit the way an actual mouse click would be.
        self._suppress_suggestion_commit = False

        self._build_widgets()

        # Size the window to whatever it actually takes to show every widget
        # without clipping, rather than a hardcoded guess -- a fixed pixel
        # size that fit fine with macOS's default fonts left the bottom
        # (status/progress) row hidden on Windows, where the fonts above
        # (particularly the ones from _widget_font's DPI-aware scaling)
        # render taller. minsize() also stops a manual resize from
        # recreating the same problem.
        self.update_idletasks()
        width = max(580, self.winfo_reqwidth())
        height = self.winfo_reqheight()
        self.geometry(f"{width}x{height}")
        self.minsize(width, height)

        # Warms the live-NSE-data caches in the background so the first
        # autocomplete lookup doesn't pay for that fetch on the UI thread --
        # by the time a user has looked at the window and started typing,
        # this has usually already finished.
        threading.Thread(target=self.symbol_resolver.warm_cache, daemon=True).start()
        threading.Thread(target=self.list_resolver.warm_cache, daemon=True).start()

    def report_callback_exception(self, exc_type, exc_value, tb):
        """Surface any unexpected error in a dialog instead of only printing to stderr.

        Tkinter's default just prints the traceback to the console, which is
        invisible to a user who launched the app by double-clicking rather
        than from a terminal -- to them it would look like a button silently
        did nothing.
        """
        import traceback

        traceback.print_exception(exc_type, exc_value, tb)
        logger.error("Unhandled error in a GUI callback", exc_info=(exc_type, exc_value, tb))
        messagebox.showerror("Something went wrong", f"{exc_type.__name__}: {exc_value}")

    def _build_widgets(self):
        """Lay out the single-window form: entry field, selection list, options, controls."""
        pad = {"padx": 10, "pady": 6}

        ctk.CTkLabel(self, text="Add a stock, index, or a saved list:").pack(anchor="w", **pad)
        entry_row = ctk.CTkFrame(self, fg_color="transparent")
        entry_row.pack(fill="x", **pad)
        self.entry_var = tk.StringVar()
        self.entry_box = ctk.CTkEntry(entry_row, textvariable=self.entry_var, width=350)
        self.entry_box.pack(side="left", fill="x", expand=True)
        self.entry_box.bind("<KeyRelease>", self._on_entry_keyrelease)
        self.entry_box.bind("<Return>", self._on_entry_return)
        self.entry_box.bind("<Down>", self._on_entry_arrow)
        self.entry_box.bind("<Up>", self._on_entry_arrow)
        ctk.CTkButton(entry_row, text="+ Add", width=70, command=self._add_from_entry).pack(
            side="left", padx=(6, 0)
        )

        # Suggestions appear here as the user types; hidden (not packed) when empty.
        self.suggestions_listbox = _styled_listbox(self, height=5, font=self._widget_font)
        self.suggestions_listbox.bind("<<ListboxSelect>>", self._on_suggestion_selected)

        self._action_row = ctk.CTkFrame(self, fg_color="transparent")
        self._action_row.pack(fill="x", **pad)
        ctk.CTkButton(self._action_row, text="Import / Paste...", command=self._open_import_dialog).pack(
            side="left"
        )
        ctk.CTkButton(self._action_row, text="Settings...", command=self._open_settings_dialog).pack(
            side="left", padx=(6, 0)
        )
        ctk.CTkButton(self._action_row, text="Help", width=60, command=self._open_help_dialog).pack(
            side="left", padx=(6, 0)
        )

        ctk.CTkLabel(self, text="Selected symbols:").pack(anchor="w", **pad)
        list_frame = ctk.CTkFrame(self, fg_color="transparent")
        list_frame.pack(fill="both", expand=True, padx=10)
        scrollbar = ctk.CTkScrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        self.selection_listbox = _styled_listbox(
            list_frame, selectmode="extended", height=8, font=self._widget_font
        )
        self.selection_listbox.config(yscrollcommand=scrollbar.set)
        self.selection_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=self.selection_listbox.yview)

        selection_buttons = ctk.CTkFrame(self, fg_color="transparent")
        selection_buttons.pack(fill="x", padx=10, pady=(2, 6))
        ctk.CTkButton(selection_buttons, text="Remove selected", command=self._remove_selected).pack(
            side="left"
        )
        ctk.CTkButton(
            selection_buttons, text="Save current selection as list...", command=self._save_as_list
        ).pack(side="left", padx=(6, 0))

        interval_row = ctk.CTkFrame(self, fg_color="transparent")
        interval_row.pack(fill="x", **pad)
        ctk.CTkLabel(interval_row, text="Interval:").pack(side="left")
        self.interval_var = tk.StringVar(value="daily")
        for label, value in INTERVAL_CHOICES:
            ctk.CTkRadioButton(interval_row, text=label, variable=self.interval_var, value=value).pack(
                side="left", padx=(10, 0)
            )

        date_row = ctk.CTkFrame(self, fg_color="transparent")
        date_row.pack(fill="x", **pad)
        ctk.CTkLabel(date_row, text="From:").pack(side="left")
        self.from_date = DateEntry(date_row, date_pattern="dd/mm/yyyy", font=self._widget_font)
        self.from_date.set_date(date.today() - timedelta(days=365))
        self.from_date.pack(side="left", padx=(4, 12))
        _fix_dateentry_dropdown_closing(self.from_date)
        ctk.CTkLabel(date_row, text="To:").pack(side="left")
        self.to_date = DateEntry(date_row, date_pattern="dd/mm/yyyy", font=self._widget_font)
        self.to_date.set_date(date.today())
        self.to_date.pack(side="left", padx=(4, 0))
        _fix_dateentry_dropdown_closing(self.to_date)

        folder_row = ctk.CTkFrame(self, fg_color="transparent")
        folder_row.pack(fill="x", **pad)
        ctk.CTkLabel(folder_row, text="Save to folder:").pack(anchor="w")
        folder_inner = ctk.CTkFrame(folder_row, fg_color="transparent")
        folder_inner.pack(fill="x")
        self.folder_var = tk.StringVar(value=str(settings.get_download_folder()))
        ctk.CTkEntry(folder_inner, textvariable=self.folder_var).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(folder_inner, text="Browse...", width=90, command=self._browse_folder).pack(
            side="left", padx=(6, 0)
        )

        filename_row = ctk.CTkFrame(self, fg_color="transparent")
        filename_row.pack(fill="x", **pad)
        ctk.CTkLabel(filename_row, text="File name (optional):").pack(anchor="w")
        # No textvariable here deliberately -- CTkEntry's placeholder_text is
        # unreliable when paired with a bound StringVar (the variable's real,
        # empty value overwrites the placeholder as soon as it's shown), so
        # this reads via .get() directly at download time instead.
        self.filename_entry = ctk.CTkEntry(
            filename_row, placeholder_text="Auto-generated from symbol(s) and dates"
        )
        self.filename_entry.pack(fill="x")

        self.download_button = ctk.CTkButton(
            self, text="Download", command=self._start_download, height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.download_button.pack(fill="x", padx=10, pady=(10, 4))

        self.status_var = tk.StringVar(value="Ready.")
        ctk.CTkLabel(self, textvariable=self.status_var, anchor="w", wraplength=540, justify="left").pack(
            fill="x", padx=10, pady=(0, 10)
        )

    # -- Entry field / autocomplete --------------------------------------------------

    def _on_entry_keyrelease(self, event):
        """Refresh the suggestions listbox below the entry field as the user types.

        This is a plain Listbox we show/hide ourselves rather than a
        ttk.Combobox's built-in dropdown -- rewriting a Combobox's `values`
        on every keystroke is known to pop its dropdown open and steal
        keyboard focus on some platforms, which made the entry field appear
        to stop accepting input after a character or two.
        """
        if event.keysym in ("Down", "Up", "Return"):
            # These are handled by _on_entry_arrow/_on_entry_return instead;
            # rebuilding the list here on their key-release would immediately
            # wipe the highlight arrow navigation just set.
            return
        text = self.entry_var.get()
        if not text.strip():
            self.suggestions_listbox.pack_forget()
            return
        symbol_matches = self.symbol_resolver.suggest(text, limit=8)
        list_matches = [n for n in self.list_resolver.all_list_names() if text.upper() in n.upper()][:5]
        suggestions = list_matches + symbol_matches
        if not suggestions:
            self.suggestions_listbox.pack_forget()
            return
        self.suggestions_listbox.delete(0, "end")
        for s in suggestions:
            self.suggestions_listbox.insert("end", s)
        self.suggestions_listbox.pack(fill="x", padx=10, before=self._action_row)

    def _on_entry_arrow(self, event):
        """Move the highlighted suggestion up/down with the arrow keys, without touching the typed text."""
        if not self.suggestions_listbox.winfo_ismapped():
            return
        size = self.suggestions_listbox.size()
        if size == 0:
            return
        current = self.suggestions_listbox.curselection()
        index = current[0] if current else -1
        if event.keysym == "Down":
            index = 0 if index == -1 else min(index + 1, size - 1)
        else:
            index = size - 1 if index == -1 else max(index - 1, 0)
        self._suppress_suggestion_commit = True
        self.suggestions_listbox.selection_clear(0, "end")
        self.suggestions_listbox.selection_set(index)
        self.suggestions_listbox.activate(index)
        self.suggestions_listbox.see(index)
        return "break"  # don't let the entry field move its cursor/selection too

    def _on_entry_return(self, _event):
        """Add the arrow-highlighted suggestion if there is one, else treat the typed text as-is."""
        if self.suggestions_listbox.winfo_ismapped():
            selection = self.suggestions_listbox.curselection()
            if selection:
                self.entry_var.set(self.suggestions_listbox.get(selection[0]))
        self._add_from_entry()

    def _on_suggestion_selected(self, _event):
        """Fill the entry field with the clicked suggestion and hide the list.

        <<ListboxSelect>> also fires for the programmatic selection changes
        _on_entry_arrow makes, which should only move the highlight, not
        commit it -- _suppress_suggestion_commit distinguishes that case
        from an actual mouse click here.
        """
        if self._suppress_suggestion_commit:
            self._suppress_suggestion_commit = False
            return
        selection = self.suggestions_listbox.curselection()
        if not selection:
            return
        self.entry_var.set(self.suggestions_listbox.get(selection[0]))
        self.suggestions_listbox.pack_forget()
        self.entry_box.focus_set()
        self.entry_box.icursor("end")

    def _add_from_entry(self):
        """Resolve the entry field's text as a list name or a single symbol, and add it."""
        text = self.entry_var.get().strip()
        if not text:
            return
        list_names = {n.upper(): n for n in self.list_resolver.all_list_names()}
        if text.upper() in list_names:
            self._add_list(list_names[text.upper()])
        else:
            self._add_symbol(text)
        self.entry_var.set("")
        self.suggestions_listbox.pack_forget()

    def _add_symbol(self, name: str):
        """Resolve and add a single stock/index by name, reporting failure via a dialog."""
        try:
            entry = entry_from_symbol(self.symbol_resolver, name)
        except SymbolNotFoundError as exc:
            suggestion_text = f" Did you mean: {', '.join(exc.suggestions)}?" if exc.suggestions else ""
            messagebox.showerror(
                "Symbol not found", f"We couldn't find '{exc.query}'.{suggestion_text or ' Try RELIANCE, NIFTY 50, or TCS.'}"
            )
            return
        self._append_entry(entry)

    def _add_list(self, list_name: str):
        """Expand a list name into its member symbols and add every resolvable one."""
        try:
            symbols = self.list_resolver.resolve(list_name)
        except ListNotFoundError:
            messagebox.showerror("List not found", f"We couldn't find a list called '{list_name}'.")
            return
        unresolved = []
        for symbol in symbols:
            try:
                self._append_entry(entry_from_symbol(self.symbol_resolver, symbol))
            except SymbolNotFoundError:
                unresolved.append(symbol)
        if unresolved:
            messagebox.showwarning(
                "Some symbols skipped",
                f"List '{list_name}' loaded {len(symbols) - len(unresolved)} of {len(symbols)} symbols. "
                f"Couldn't recognize: {', '.join(unresolved)} — check for typos.",
            )

    def _append_entry(self, entry: Entry):
        """Add an Entry to the selection list, skipping exact duplicates."""
        if any(e.ticker == entry.ticker for e in self.entries):
            return
        self.entries.append(entry)
        self.selection_listbox.insert("end", entry.display_name)

    def _remove_selected(self):
        """Remove the currently highlighted rows from the selection list."""
        for index in reversed(self.selection_listbox.curselection()):
            self.selection_listbox.delete(index)
            del self.entries[index]

    # -- Import / paste dialog --------------------------------------------------------

    def _open_import_dialog(self):
        """Open a small dialog for pasting comma/newline-separated symbols or choosing a file."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Import / Paste symbols")
        dialog.geometry("420x300")

        ctk.CTkLabel(dialog, text="Paste symbols (comma or newline separated):").pack(
            anchor="w", padx=10, pady=(10, 4)
        )
        text_box = ctk.CTkTextbox(dialog, height=160)
        text_box.pack(fill="both", expand=True, padx=10)

        def import_pasted():
            symbols = parse_pasted_text(text_box.get("1.0", "end"))
            dialog.destroy()
            self._add_many(symbols, source_label="pasted text")

        def import_from_file():
            path = filedialog.askopenfilename(filetypes=[("Spreadsheet files", "*.csv *.xlsx *.xls")])
            if not path:
                return
            try:
                symbols = parse_file(Path(path))
            except Exception:
                messagebox.showerror(
                    "Import failed",
                    "We couldn't find a column of symbols in that file. "
                    "Make sure one column is headed 'Symbol' (or is the first column).",
                )
                return
            dialog.destroy()
            self._add_many(symbols, source_label=Path(path).name)

        button_row = ctk.CTkFrame(dialog, fg_color="transparent")
        button_row.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(button_row, text="Add pasted symbols", command=import_pasted).pack(side="left")
        ctk.CTkButton(button_row, text="Choose a file...", command=import_from_file).pack(
            side="left", padx=(6, 0)
        )

    def _add_many(self, symbols: list[str], source_label: str):
        """Resolve and add several symbols at once, reporting any that failed to resolve."""
        unresolved = []
        for symbol in symbols:
            try:
                self._append_entry(entry_from_symbol(self.symbol_resolver, symbol))
            except SymbolNotFoundError:
                unresolved.append(symbol)
        if unresolved:
            resolved_count = len(symbols) - len(unresolved)
            messagebox.showwarning(
                "Some symbols skipped",
                f"Imported {resolved_count} of {len(symbols)} symbols from '{source_label}'. "
                f"Couldn't recognize: {', '.join(unresolved)} — check for typos.",
            )

    # -- Save as list --------------------------------------------------------------

    def _save_as_list(self):
        """Prompt for a name and save the current selection as a custom list."""
        if not self.entries:
            messagebox.showinfo("Nothing to save", "Add at least one stock or index before saving a list.")
            return
        name = ctk.CTkInputDialog(title="Save as list", text="Name for this list:").get_input()
        if not name:
            return
        try:
            self.list_resolver.save_custom_list(name, [e.display_name for e in self.entries])
        except WorkbookLockedError as exc:
            messagebox.showerror("Couldn't save list", str(exc))
            return
        messagebox.showinfo("List saved", f"Saved '{name}' with {len(self.entries)} symbols.")

    # -- Folder picker ----------------------------------------------------------------

    def _browse_folder(self):
        """Open a native folder picker and update the output-folder field."""
        chosen = filedialog.askdirectory(initialdir=self.folder_var.get())
        if chosen:
            self.folder_var.set(chosen)

    # -- Settings ---------------------------------------------------------------------

    def _open_settings_dialog(self):
        """Open a small dialog to change the persistent default download/lists folders."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Settings")
        dialog.geometry("420x200")

        ctk.CTkLabel(dialog, text="Default download folder:").pack(anchor="w", padx=10, pady=(10, 0))
        download_row = ctk.CTkFrame(dialog, fg_color="transparent")
        download_row.pack(fill="x", padx=10)
        download_var = tk.StringVar(value=str(settings.get_download_folder()))
        ctk.CTkEntry(download_row, textvariable=download_var).pack(side="left", fill="x", expand=True)

        def browse_download():
            """Fill the download-folder field via a native folder picker."""
            chosen = filedialog.askdirectory(initialdir=download_var.get())
            if chosen:
                download_var.set(chosen)

        ctk.CTkButton(download_row, text="Browse...", width=90, command=browse_download).pack(
            side="left", padx=(6, 0)
        )

        ctk.CTkLabel(dialog, text="Custom lists folder:").pack(anchor="w", padx=10, pady=(10, 0))
        lists_row = ctk.CTkFrame(dialog, fg_color="transparent")
        lists_row.pack(fill="x", padx=10)
        lists_var = tk.StringVar(value=str(settings.get_lists_folder()))
        ctk.CTkEntry(lists_row, textvariable=lists_var).pack(side="left", fill="x", expand=True)

        def browse_lists():
            """Fill the lists-folder field via a native folder picker."""
            chosen = filedialog.askdirectory(initialdir=lists_var.get())
            if chosen:
                lists_var.set(chosen)

        ctk.CTkButton(lists_row, text="Browse...", width=90, command=browse_lists).pack(
            side="left", padx=(6, 0)
        )

        def save():
            """Persist both folders and apply them immediately, without needing a restart."""
            download_path = Path(download_var.get().strip())
            lists_path = Path(lists_var.get().strip())
            settings.set_download_folder(download_path)
            settings.set_lists_folder(lists_path)
            self.folder_var.set(str(download_path))
            self.list_resolver.set_workbook_path(lists_path / "My Lists.xlsx")
            dialog.destroy()

        ctk.CTkButton(dialog, text="Save", command=save).pack(pady=16)

    # -- Help -----------------------------------------------------------------------

    def _open_help_dialog(self):
        """Open a dialog rendering HELP.md: what the app supports and common failures."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Help")
        dialog.geometry("560x520")

        textbox = ctk.CTkTextbox(dialog, wrap="word")
        textbox.pack(fill="both", expand=True, padx=10, pady=10)

        try:
            content = HELP_PATH.read_text(encoding="utf-8")
        except OSError:
            content = "Couldn't load the help file."
            logger.warning("Couldn't read HELP.md from %s", HELP_PATH, exc_info=True)

        _insert_markdown(textbox, content)
        textbox.configure(state="disabled")

        ctk.CTkButton(dialog, text="Close", command=dialog.destroy).pack(pady=(0, 10))

    # -- Download ---------------------------------------------------------------------

    def _start_download(self):
        """Validate the form and kick off the download on a background thread."""
        if not self.entries:
            messagebox.showinfo("Nothing to download", "Add at least one symbol first.")
            return
        start = self.from_date.get_date()
        end = self.to_date.get_date()
        interval = self.interval_var.get()
        error = validate_date_range(interval, start, end)
        if error:
            messagebox.showerror("Invalid date range", error)
            return
        output_dir = Path(self.folder_var.get())
        if not output_dir.exists() or not output_dir.is_dir():
            messagebox.showerror("Invalid folder", "Please choose a valid folder to save to.")
            return

        self.download_button.configure(state="disabled")
        entries = list(self.entries)
        filename = self.filename_entry.get()
        thread = threading.Thread(
            target=self._run_download, args=(entries, interval, start, end, output_dir, filename), daemon=True
        )
        thread.start()

    def _run_download(self, entries, interval, start, end, output_dir, filename):
        """Run the fetch/write pipeline off the UI thread, posting progress back via `after`."""

        def on_progress(i, total, name):
            self.after(0, lambda: self.status_var.set(f"Fetching {name} ({i}/{total})..."))

        try:
            result = download_all(
                entries, interval, start, end, output_dir, filename=filename, on_progress=on_progress
            )
        except Exception as exc:
            self.after(0, lambda: self._download_failed(str(exc)))
            return
        self.after(0, lambda: self._download_finished(result))

    def _download_failed(self, message: str):
        """Show an unexpected failure and re-enable the Download button."""
        self.download_button.configure(state="normal")
        messagebox.showerror("Download failed", message)
        self.status_var.set("Ready.")

    def _download_finished(self, result):
        """Report the final outcome (success/partial/failure) and re-enable the Download button."""
        self.download_button.configure(state="normal")
        if not result.succeeded:
            reasons = "; ".join(f"{name}: {reason}" for name, reason in result.failed)
            self.status_var.set(f"No data downloaded. {reasons}")
            return

        clamp_note = (
            f" (5-minute/hourly data was limited to {result.clamped_start.isoformat()} onward.)"
            if result.was_clamped
            else ""
        )
        if result.failed:
            skipped = "; ".join(f"{name} ({reason})" for name, reason in result.failed)
            self.status_var.set(
                f"Saved {len(result.succeeded)} of {len(result.succeeded) + len(result.failed)} symbols to "
                f"{result.output_path}. Skipped: {skipped}.{clamp_note}"
            )
        else:
            self.status_var.set(f"Saved to {result.output_path}.{clamp_note}")


if __name__ == "__main__":
    applog.setup_logging()
    try:
        App().mainloop()
    except Exception:
        logger.exception("Fatal startup error")
        raise
