"""Tkinter desktop app: NSE Data Fetcher.

A single-window form (per docs/DESIGN.md §11) that lets a non-technical user
add stocks/indices/lists, pick an interval and date range, and download
everything into one Excel workbook.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from datetime import date, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from tkcalendar import DateEntry

import applog
from downloader import Entry, download_all, entry_from_symbol
from importer import parse_file, parse_pasted_text
from lists import ListNotFoundError, ListResolver, WorkbookLockedError, default_documents_dir
from symbols import SymbolNotFoundError, SymbolResolver

logger = logging.getLogger(__name__)

INTERVAL_CHOICES = [("5 min", "5min"), ("15 min", "15min"), ("1 hour", "1hour"), ("Daily", "daily")]


class App(tk.Tk):
    """The application's single top-level window."""

    def __init__(self):
        """Build all widgets and load the symbol/list resolvers."""
        super().__init__()
        self.title("NSE Data Fetcher")
        self.geometry("560x620")

        self.symbol_resolver = SymbolResolver()
        self.list_resolver = ListResolver()
        self.entries: list[Entry] = []

        self._build_widgets()

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

        tk.Label(self, text="Add a stock, index, or a saved list:").pack(anchor="w", **pad)
        entry_row = tk.Frame(self)
        entry_row.pack(fill="x", **pad)
        self.entry_var = tk.StringVar()
        self.entry_box = tk.Entry(entry_row, textvariable=self.entry_var, width=35)
        self.entry_box.pack(side="left", fill="x", expand=True)
        self.entry_box.bind("<KeyRelease>", self._on_entry_keyrelease)
        self.entry_box.bind("<Return>", lambda e: self._add_from_entry())
        tk.Button(entry_row, text="+ Add", command=self._add_from_entry).pack(side="left", padx=(6, 0))

        # Suggestions appear here as the user types; hidden (not packed) when empty.
        self.suggestions_listbox = tk.Listbox(self, height=5)
        self.suggestions_listbox.bind("<<ListboxSelect>>", self._on_suggestion_selected)

        self._action_row = tk.Frame(self)
        self._action_row.pack(fill="x", **pad)
        tk.Button(self._action_row, text="Import / Paste...", command=self._open_import_dialog).pack(side="left")

        tk.Label(self, text="Selected symbols:").pack(anchor="w", **pad)
        list_frame = tk.Frame(self)
        list_frame.pack(fill="both", expand=True, padx=10)
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        self.selection_listbox = tk.Listbox(
            list_frame, selectmode="extended", yscrollcommand=scrollbar.set, height=8
        )
        self.selection_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.selection_listbox.yview)

        selection_buttons = tk.Frame(self)
        selection_buttons.pack(fill="x", padx=10, pady=(2, 6))
        tk.Button(selection_buttons, text="Remove selected", command=self._remove_selected).pack(side="left")
        tk.Button(
            selection_buttons, text="Save current selection as list...", command=self._save_as_list
        ).pack(side="left", padx=(6, 0))

        interval_row = tk.Frame(self)
        interval_row.pack(fill="x", **pad)
        tk.Label(interval_row, text="Interval:").pack(side="left")
        self.interval_var = tk.StringVar(value="daily")
        for label, value in INTERVAL_CHOICES:
            tk.Radiobutton(interval_row, text=label, variable=self.interval_var, value=value).pack(side="left")

        date_row = tk.Frame(self)
        date_row.pack(fill="x", **pad)
        tk.Label(date_row, text="From:").pack(side="left")
        self.from_date = DateEntry(date_row, date_pattern="dd/mm/yyyy")
        self.from_date.set_date(date.today() - timedelta(days=365))
        self.from_date.pack(side="left", padx=(4, 12))
        tk.Label(date_row, text="To:").pack(side="left")
        self.to_date = DateEntry(date_row, date_pattern="dd/mm/yyyy")
        self.to_date.set_date(date.today())
        self.to_date.pack(side="left", padx=(4, 0))

        folder_row = tk.Frame(self)
        folder_row.pack(fill="x", **pad)
        tk.Label(folder_row, text="Save to folder:").pack(anchor="w")
        folder_inner = tk.Frame(folder_row)
        folder_inner.pack(fill="x")
        self.folder_var = tk.StringVar(value=str(default_documents_dir()))
        tk.Entry(folder_inner, textvariable=self.folder_var).pack(side="left", fill="x", expand=True)
        tk.Button(folder_inner, text="Browse...", command=self._browse_folder).pack(side="left", padx=(6, 0))

        self.download_button = tk.Button(self, text="Download", command=self._start_download, height=2)
        self.download_button.pack(fill="x", padx=10, pady=(10, 4))

        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(self, textvariable=self.status_var, anchor="w", wraplength=520, justify="left").pack(
            fill="x", padx=10, pady=(0, 10)
        )

    # -- Entry field / autocomplete --------------------------------------------------

    def _on_entry_keyrelease(self, _event):
        """Refresh the suggestions listbox below the entry field as the user types.

        This is a plain Listbox we show/hide ourselves rather than a
        ttk.Combobox's built-in dropdown -- rewriting a Combobox's `values`
        on every keystroke is known to pop its dropdown open and steal
        keyboard focus on some platforms, which made the entry field appear
        to stop accepting input after a character or two.
        """
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

    def _on_suggestion_selected(self, _event):
        """Fill the entry field with the clicked suggestion and hide the list."""
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
        dialog = tk.Toplevel(self)
        dialog.title("Import / Paste symbols")
        dialog.geometry("420x300")

        tk.Label(dialog, text="Paste symbols (comma or newline separated):").pack(anchor="w", padx=10, pady=(10, 4))
        text_box = tk.Text(dialog, height=8)
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

        button_row = tk.Frame(dialog)
        button_row.pack(fill="x", padx=10, pady=10)
        tk.Button(button_row, text="Add pasted symbols", command=import_pasted).pack(side="left")
        tk.Button(button_row, text="Choose a file...", command=import_from_file).pack(side="left", padx=(6, 0))

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
        name = simpledialog.askstring("Save as list", "Name for this list:")
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

    # -- Download ---------------------------------------------------------------------

    def _start_download(self):
        """Validate the form and kick off the download on a background thread."""
        if not self.entries:
            messagebox.showinfo("Nothing to download", "Add at least one symbol first.")
            return
        start = self.from_date.get_date()
        end = self.to_date.get_date()
        if start > end:
            messagebox.showerror("Invalid date range", "The 'From' date must be before the 'To' date.")
            return
        output_dir = Path(self.folder_var.get())
        if not output_dir.exists() or not output_dir.is_dir():
            messagebox.showerror("Invalid folder", "Please choose a valid folder to save to.")
            return

        self.download_button.config(state="disabled")
        entries = list(self.entries)
        interval = self.interval_var.get()
        thread = threading.Thread(
            target=self._run_download, args=(entries, interval, start, end, output_dir), daemon=True
        )
        thread.start()

    def _run_download(self, entries, interval, start, end, output_dir):
        """Run the fetch/write pipeline off the UI thread, posting progress back via `after`."""

        def on_progress(i, total, name):
            self.after(0, lambda: self.status_var.set(f"Fetching {name} ({i}/{total})..."))

        try:
            result = download_all(entries, interval, start, end, output_dir, on_progress=on_progress)
        except Exception as exc:
            self.after(0, lambda: self._download_failed(str(exc)))
            return
        self.after(0, lambda: self._download_finished(result))

    def _download_failed(self, message: str):
        """Show an unexpected failure and re-enable the Download button."""
        self.download_button.config(state="normal")
        messagebox.showerror("Download failed", message)
        self.status_var.set("Ready.")

    def _download_finished(self, result):
        """Report the final outcome (success/partial/failure) and re-enable the Download button."""
        self.download_button.config(state="normal")
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
