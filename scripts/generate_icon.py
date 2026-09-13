"""Generates the NSE Data Fetcher app icon: a rounded square in the app's
CTk blue theme with a simple white upward candlestick/bar-chart glyph.

The squircle is drawn inset within the canvas (Apple's Big Sur icon
template: ~824px of artwork centered in a 1024px canvas) rather than
filling it edge-to-edge -- macOS doesn't add any margin of its own around
a .icns image, so a full-bleed icon renders visibly larger than every
other Dock/Cmd+Tab icon, which all follow this same inset convention.

Run with `python scripts/generate_icon.py` (needs Pillow: `pip install
pillow`, not a runtime dependency of the app itself) whenever the icon
design changes; it overwrites src/assets/icon.{png,ico,icns}.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).parent.parent / "src" / "assets"

CANVAS_SIZE = 1024
CONTENT_SIZE = 824  # Apple's Big Sur icon template proportion (~80.5% of canvas)
MARGIN = (CANVAS_SIZE - CONTENT_SIZE) // 2

BG_TOP = (59, 142, 208, 255)     # CTkButton light-mode fg_color "#3B8ED0"
BG_BOTTOM = (31, 106, 165, 255)  # CTkButton dark-mode fg_color "#1F6AA5"
WHITE = (255, 255, 255, 255)


def rounded_square_gradient(size: int, radius: int) -> Image.Image:
    """Return a vertical-gradient rounded square from BG_TOP to BG_BOTTOM, sized `size` x `size`."""
    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gradient = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for y in range(size):
        t = y / (size - 1)
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        ImageDraw.Draw(gradient).line([(0, y), (size, y)], fill=(r, g, b, 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    base.paste(gradient, (0, 0), mask)
    return base


def draw_candlesticks(img: Image.Image) -> None:
    """Draw three simple ascending candlestick bars -- a stock-data motif -- onto `img` in place."""
    draw = ImageDraw.Draw(img)
    size = img.width
    bar_width = size * 0.11
    # (center_x_fraction, bar_top_fraction, bar_bottom_fraction, wick_top_fraction, wick_bottom_fraction)
    bars = [
        (0.30, 0.62, 0.78, 0.56, 0.82),
        (0.50, 0.46, 0.62, 0.40, 0.68),
        (0.70, 0.26, 0.46, 0.20, 0.52),
    ]
    for cx_frac, top_frac, bottom_frac, wick_top_frac, wick_bottom_frac in bars:
        cx = size * cx_frac
        draw.line(
            [(cx, size * wick_top_frac), (cx, size * wick_bottom_frac)],
            fill=WHITE, width=int(size * 0.014),
        )
        draw.rounded_rectangle(
            [cx - bar_width / 2, size * top_frac, cx + bar_width / 2, size * bottom_frac],
            radius=size * 0.02, fill=WHITE,
        )


def main():
    """Build the master icon and export the PNG/ICO/ICNS files the app and its builds need."""
    content = rounded_square_gradient(CONTENT_SIZE, radius=int(CONTENT_SIZE * 0.22))
    draw_candlesticks(content)

    icon = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    icon.paste(content, (MARGIN, MARGIN), content)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    icon.save(OUT_DIR / "icon.png")

    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icon.save(OUT_DIR / "icon.ico", sizes=ico_sizes)

    icon.save(OUT_DIR / "icon.icns")

    print(f"Wrote icon.png, icon.ico, icon.icns to {OUT_DIR}")


if __name__ == "__main__":
    main()
