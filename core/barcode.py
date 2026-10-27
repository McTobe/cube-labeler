"""
Code 128 barcodes, drawn in printer dots.

Code 128 holds any plain ASCII text, and packs runs of digits two to a symbol (code set C),
so part numbers and article numbers stay short enough for small labels. Everything here is
pure Python, so the desktop app and the web version (Pyodide) draw the same bars.
"""

from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

# Bar and space widths, in modules, for symbol values 0-105; each adds up to 11 modules
PATTERNS = (
    "212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 "
    "221312 231212 112232 122132 122231 113222 123122 123221 223211 221132 "
    "221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 "
    "212123 212321 232121 111323 131123 131321 112313 132113 132311 211313 "
    "231113 231311 112133 112331 132131 113123 113321 133121 313121 211331 "
    "231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 "
    "314111 221411 431111 111224 111422 121124 121421 141122 141221 112214 "
    "112412 122114 122411 142112 142211 241211 221114 413111 241112 134111 "
    "111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 "
    "214121 412121 111143 111341 131141 114113 114311 411113 411311 113141 "
    "114131 311141 411131 211412 211214 211232"
).split()
STOP = "2331112"

START_A, START_B, START_C = 103, 104, 105
CODE_A, CODE_B, CODE_C = 101, 100, 99

# Narrowest bar, in printer dots: 2 dots is 0.28 mm at 180 dpi, which phone cameras and
# hand scanners read reliably (1 dot, 0.14 mm, smudges on thermal tape)
MODULE_DOTS = 2
# Blank space a scanner needs on each side of the bars, in modules
QUIET_MODULES = 10


def unsupported_chars(data: str) -> str:
    """The characters Code 128 can't hold (anything outside ASCII), each once, in order."""
    seen = []
    for ch in data:
        if ord(ch) > 127 and ch not in seen:
            seen.append(ch)
    return "".join(seen)


def _digit_run(data: str, start: int) -> int:
    end = start
    while end < len(data) and data[end].isdigit():
        end += 1
    return end - start


def _value(ch: str, code: str) -> int:
    o = ord(ch)
    if code == "A":
        return o + 64 if o < 32 else o - 32
    return o - 32


def encode(data: str) -> List[int]:
    """
    Symbol values for data, from the start symbol to the check symbol (without the stop).
    Runs of at least four digits (six in the middle of text) go in code set C, the rest in B,
    or A for control characters. Raises ValueError for characters outside ASCII.
    """
    if not data:
        raise ValueError("Nothing to encode")
    bad = unsupported_chars(data)
    if bad:
        raise ValueError(f"Code 128 can't hold {bad}")

    def wants_c(i: int) -> bool:
        run = _digit_run(data, i)
        at_edge = i == 0 or i + run == len(data)
        # Two digits on their own are shorter in C too
        return run >= (4 if at_edge else 6) or (i == 0 and run == len(data) == 2)

    def text_code(i: int) -> str:
        # A only for control characters that come before any lower case letter
        for ch in data[i:]:
            if ord(ch) < 32:
                return "A"
            if "`" <= ch:
                return "B"
        return "B"

    values: List[int] = []
    i = 0
    if wants_c(0):
        code = "C"
        values.append(START_C)
    else:
        code = text_code(0)
        values.append(START_A if code == "A" else START_B)

    while i < len(data):
        if code == "C":
            if _digit_run(data, i) >= 2:
                values.append(int(data[i:i + 2]))
                i += 2
                continue
            code = text_code(i)
            values.append(CODE_A if code == "A" else CODE_B)
            continue
        if data[i].isdigit() and wants_c(i):
            # An odd run keeps its first digit in this code set, so C gets pairs
            if _digit_run(data, i) % 2:
                values.append(_value(data[i], code))
                i += 1
            values.append(CODE_C)
            code = "C"
            continue
        ch = data[i]
        if code == "B" and ord(ch) < 32:
            code = "A"
            values.append(CODE_A)
        elif code == "A" and "`" <= ch:
            code = "B"
            values.append(CODE_B)
        values.append(_value(ch, code))
        i += 1

    check = (values[0] + sum(v * n for n, v in enumerate(values[1:], 1))) % 103
    values.append(check)
    return values


def modules(data: str) -> List[int]:
    """The bars and spaces of the whole symbol, bar first, in modules (no quiet zones)."""
    widths = "".join(PATTERNS[v] for v in encode(data)) + STOP
    return [int(w) for w in widths]


def render(
    data: str, height: int, show_text: bool = True, font: Optional[ImageFont.FreeTypeFont] = None,
    module: int = MODULE_DOTS,
) -> Optional[Image.Image]:
    """
    The barcode for data as a grayscale image `height` dots tall, black bars on white, with
    the quiet zones on both sides. With show_text the text is written under the bars in
    `font` (sized to fit). Returns None when there's nothing to draw or data won't encode.
    """
    data = data.strip()
    if not data or unsupported_chars(data):
        return None
    widths = modules(data)
    quiet = QUIET_MODULES * module
    bars_w = sum(widths) * module
    img = Image.new("L", (bars_w + 2 * quiet, max(height, 8)), 255)
    draw = ImageDraw.Draw(img)

    text_h = 0
    text_font = None
    # The text needs about a fifth of the height to be readable; on very low tape it's left out
    if show_text and font is not None and height >= 28:
        text_h = max(int(height * 0.26), 9)
        text_font = font.font_variant(size=text_h + 2)
        # Shrink until the text fits under the bars
        while text_font.size > 6 and (
            draw.textbbox((0, 0), data, font=text_font)[3] - draw.textbbox((0, 0), data, font=text_font)[1] > text_h
            or draw.textlength(data, font=text_font) > img.width
        ):
            text_font = text_font.font_variant(size=text_font.size - 1)
    bars_h = img.height - (text_h + 2 if text_font else 0)

    x = quiet
    for n, w in enumerate(widths):
        if n % 2 == 0:
            draw.rectangle([x, 0, x + w * module - 1, bars_h - 1], fill=0)
        x += w * module

    if text_font:
        left, top, right, bottom = draw.textbbox((0, 0), data, font=text_font)
        tx = (img.width - (right - left)) // 2 - left
        ty = img.height - (bottom - top) - top
        draw.text((tx, ty), data, font=text_font, fill=0)
    return img
