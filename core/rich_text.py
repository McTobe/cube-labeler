#!/usr/bin/env python3
"""
Styled text for text labels. The styling is simple markdown written in the label text
itself, so templates, the queue and the web version keep it as plain text.

Inside a line:   **bold**   *italic*   __underline__   ==inverted== (white on black)
At a line start: "# " large, "## " medium, "-# " small,
                 "<< " left, ">< " centre, ">> " right (otherwise the label's alignment)
On its own line: "---" starts a new column with a divider line between them
A backslash keeps a marker as plain text, as in "M3 \\* 8".
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw

from core.font_manager import font_manager

SIZE_PREFIXES = [("## ", "medium"), ("# ", "large"), ("-# ", "small")]
SIZE_FACTORS = {"large": 1.6, "medium": 1.3, "normal": 1.0, "small": 0.7}
ALIGN_PREFIXES = [("<< ", "left"), (">< ", "center"), (">> ", "right")]
COLUMN_BREAK = "---"

# Longest first, so "**" is read as bold and not as two italic markers
INLINE_MARKERS = [("**", "bold"), ("__", "underline"), ("==", "invert"), ("*", "italic")]
ESCAPABLE = "\\*_=#<>-"

ITALIC_SLANT = 0.2  # Horizontal shift per dot of height for fonts without an italic file


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    invert: bool = False


@dataclass
class Line:
    runs: List[Run] = field(default_factory=list)
    size: str = "normal"
    align: Optional[str] = None  # None: the label's alignment

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)

    @property
    def factor(self) -> float:
        return SIZE_FACTORS[self.size]


@dataclass
class RichText:
    columns: List[List[Line]]

    @property
    def lines(self) -> List[Line]:
        return [line for col in self.columns for line in col]

    @property
    def has_text(self) -> bool:
        return any(line.text.strip() for line in self.lines)


def _opens(text: str, start: int, marker: str) -> bool:
    """A marker opens a style only if text follows it and the same marker closes it later."""
    if start >= len(text) or text[start] == " ":
        return False
    idx = text.find(marker, start + 1)
    while idx != -1:
        if text[idx - 1] != " " and text[idx - 1] != "\\":
            return True
        idx = text.find(marker, idx + 1)
    return False


def parse_inline(text: str) -> List[Run]:
    runs: List[Run] = []
    state: Dict[str, bool] = {"bold": False, "italic": False, "underline": False, "invert": False}
    buf: List[str] = []

    def flush():
        if buf:
            runs.append(Run("".join(buf), **state))
            buf.clear()

    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text) and text[i + 1] in ESCAPABLE:
            buf.append(text[i + 1])
            i += 2
            continue
        for marker, attr in INLINE_MARKERS:
            if not text.startswith(marker, i):
                continue
            end = i + len(marker)
            if state[attr] and i > 0 and text[i - 1] != " ":
                flush()
                state[attr] = False
            elif not state[attr] and _opens(text, end, marker):
                flush()
                state[attr] = True
            else:
                continue
            i = end
            break
        else:
            buf.append(ch)
            i += 1
    flush()
    return runs


def parse_line(raw: str) -> Line:
    size, align, rest = _split_prefixes(raw)
    return Line(parse_inline(rest), size, align)


def parse(text: str) -> RichText:
    """Parses label text into columns of styled lines. Literal "\\n" counts as a new line."""
    columns: List[List[Line]] = [[]]
    for raw in text.replace("\\n", "\n").split("\n"):
        if raw.strip() == COLUMN_BREAK:
            columns.append([])
        else:
            columns[-1].append(parse_line(raw))
    return RichText([col for col in columns if col] or [[Line()]])


def plain_text(text: str) -> str:
    """The label text without its styling markers, for summaries and lists."""
    doc = parse(text)
    return "\n".join(line.text for line in doc.lines)


# --- Layout ---------------------------------------------------------------------------------

def _bold_px(size: int) -> int:
    return max(1, round(size * 0.04))


def _invert_pad(size: int) -> int:
    return max(2, round(size * 0.12))


def _underline(size: int) -> Tuple[int, int]:
    """Offset below the baseline and thickness of an underline."""
    return max(2, round(size * 0.1)), max(1, round(size * 0.06))


class TextLayout:
    """Measures and draws parsed label text with one font family."""

    def __init__(self, doc: RichText, font_name: str, stroke_width: int = 0, line_spacing: float = 1.2,
                 align: str = "center"):
        self.doc = doc
        self.font_name = font_name
        self.stroke = stroke_width
        self.spacing = line_spacing
        self.align = align
        # All lines share one reference text, so lines of the same size are the same height
        self.ref_text = "".join(line.text for line in doc.lines).strip() or "Ag"

    def _size(self, line: Line, base: int) -> int:
        return max(int(round(base * line.factor)), 4)

    def _line_box(self, line: Line, base: int) -> Tuple[int, int]:
        """Top (negative) and bottom of a line relative to its baseline."""
        size = self._size(line, base)
        font = font_manager.load_font(self.font_name, size)
        _, top, _, bottom = font.getbbox(self.ref_text, anchor="ls")
        runs = line.runs
        extra = self.stroke + (_bold_px(size) if any(r.bold for r in runs) else 0)
        top, bottom = top - extra, bottom + extra
        if any(r.underline for r in runs):
            offset, thick = _underline(size)
            bottom = max(bottom, offset + thick)
        if any(r.invert for r in runs):
            pad = _invert_pad(size)
            top, bottom = top - pad, bottom + pad
        return top, bottom

    def _column_heights(self, column: List[Line], base: int) -> List[int]:
        return [b - t for t, b in (self._line_box(line, base) for line in column)]

    def _gap(self, h1: int, h2: int) -> int:
        return int(round((self.spacing - 1.0) * max(h1, h2)))

    def column_height(self, column: List[Line], base: int) -> int:
        heights = self._column_heights(column, base)
        return sum(heights) + sum(self._gap(a, b) for a, b in zip(heights, heights[1:]))

    def height(self, base: int) -> int:
        return max(self.column_height(col, base) for col in self.doc.columns)

    def fit_size(self, target_height: int) -> int:
        """Largest base size whose text fits target_height."""
        low, high, best = 6, max(target_height * 2, 6), 6
        while low <= high:
            mid = (low + high) // 2
            if self.height(mid) <= target_height:
                best, low = mid, mid + 1
            else:
                high = mid - 1
        return best

    def size_for_cap_height(self, dots: float) -> int:
        """Base size whose capital letters are `dots` tall, as a letter height on a label maker."""
        probe = 200
        font = font_manager.load_font(self.font_name, probe)
        _, top, _, bottom = font.getbbox("H", anchor="ls")
        return max(int(round(probe * dots / max(bottom - top, 1))), 4)

    def cap_height(self, base: int) -> int:
        """How tall the capital letters of a normal line are at this base size, in dots."""
        _, top, _, bottom = font_manager.load_font(self.font_name, base).getbbox("H", anchor="ls")
        return bottom - top

    # --- Drawing

    def _render_run(self, run: Run, size: int, top: int, bottom: int) -> Tuple[Image.Image, int, int]:
        """Draws one run as a mask. Returns (mask, x of the text origin in it, advance)."""
        font, fake_bold, fake_italic = font_manager.load_styled_font(self.font_name, size, run.bold, run.italic)
        stroke = self.stroke + (_bold_px(size) if fake_bold else 0)
        height = bottom - top
        baseline = -top
        pad = _invert_pad(size) if run.invert else 0
        slant_left = math.ceil(ITALIC_SLANT * bottom) if fake_italic else 0
        slant_right = math.ceil(ITALIC_SLANT * -top) if fake_italic else 0
        text_w = int(math.ceil(font.getlength(run.text))) + 2 * stroke
        origin = pad + slant_left + stroke
        width = origin + text_w + slant_right + pad

        mask = Image.new("L", (max(width, 1), max(height, 1)), 255 if run.invert else 0)
        draw = ImageDraw.Draw(mask)
        ink = 0 if run.invert else 255
        draw.text((origin, baseline), run.text, font=font, fill=ink, anchor="ls",
                  stroke_width=stroke, stroke_fill=ink)
        if run.underline:
            offset, thick = _underline(size)
            x0, x1 = origin - stroke, origin + text_w - stroke - 1
            draw.rectangle([x0, baseline + offset, x1, baseline + offset + thick - 1], fill=ink)
        if fake_italic:
            mask = mask.transform(
                mask.size, Image.Transform.AFFINE,
                (1, ITALIC_SLANT, -ITALIC_SLANT * baseline, 0, 1, 0),
                resample=Image.Resampling.BICUBIC, fillcolor=255 if run.invert else 0,
            )
        advance = text_w + 2 * pad
        return mask, origin - stroke - pad, advance

    def render_line(self, line: Line, base: int) -> Image.Image:
        """Draws one line, cropped to its ink (leading spaces count as indentation)."""
        size = self._size(line, base)
        top, bottom = self._line_box(line, base)
        height = bottom - top
        if not line.text.strip():
            return Image.new("L", (0, height), 0)

        parts = [self._render_run(run, size, top, bottom) for run in line.runs]
        lead = max(start for _, start, _ in parts)
        width = lead + sum(adv for _, _, adv in parts) + max(m.width for m, _, _ in parts)
        out = Image.new("L", (width, height), 0)
        x = lead
        for run, (mask, start, adv) in zip(line.runs, parts):
            pos = x - start
            if run.invert:
                out.paste(mask, (pos, 0))
            else:
                region = out.crop((pos, 0, pos + mask.width, height))
                out.paste(ImageChops.lighter(region, mask), (pos, 0))
            x += adv

        bbox = out.getbbox()
        if not bbox:
            return Image.new("L", (0, height), 0)
        first = line.runs[0]
        left = bbox[0]
        if first.text.startswith(" ") and not first.invert:
            font, _, _ = font_manager.load_styled_font(self.font_name, size, first.bold, first.italic)
            indent = int(round(font.getlength(first.text[: len(first.text) - len(first.text.lstrip(" "))])))
            left = max(bbox[0] - indent, 0)
        return out.crop((left, 0, bbox[2], height))

    def _render_column(self, column: List[Line], base: int) -> Image.Image:
        images = [self.render_line(line, base) for line in column]
        heights = [img.height for img in images]
        width = max([img.width for img in images] + [1])
        total = sum(heights) + sum(self._gap(a, b) for a, b in zip(heights, heights[1:]))
        out = Image.new("L", (width, max(total, 1)), 0)
        y = 0
        for i, (line, img) in enumerate(zip(column, images)):
            align = line.align or self.align
            if align == "left":
                x = 0
            elif align == "right":
                x = width - img.width
            else:
                x = (width - img.width) // 2
            if img.width:
                out.paste(img, (x, y))
            y += img.height
            if i + 1 < len(images):
                y += self._gap(img.height, heights[i + 1])
        return out

    def render(self, base: int) -> Image.Image:
        """Draws the whole text block as a mask (255 = ink), columns side by side."""
        cols = [self._render_column(col, base) for col in self.doc.columns]
        if len(cols) == 1:
            return cols[0]
        height = max(c.height for c in cols)
        gap = max(6, round(base * 0.3))
        line_w = max(1, round(base * 0.05))
        width = sum(c.width for c in cols) + (len(cols) - 1) * (2 * gap + line_w)
        out = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(out)
        x = 0
        for i, col in enumerate(cols):
            out.paste(col, (x, (height - col.height) // 2))
            x += col.width
            if i + 1 < len(cols):
                x += gap
                draw.rectangle([x, 0, x + line_w - 1, height - 1], fill=255)
                x += line_w + gap
        return out


# --- Editing helpers (used by the editor toolbar) ------------------------------------------

STYLE_MARKERS = {"bold": "**", "italic": "*", "underline": "__", "invert": "=="}


def _run_of(text: str, pos: int, step: int, char: str) -> int:
    """How many times char repeats from pos going left (step -1) or right (step 1)."""
    count = 0
    i = pos - 1 if step < 0 else pos
    while 0 <= i < len(text) and text[i] == char:
        count += 1
        i += step
    return count


def _is_wrapped(text: str, start: int, end: int, marker: str) -> bool:
    if marker[0] == "*":
        before, after = _run_of(text, start, -1, "*"), _run_of(text, end, 1, "*")
        if marker == "*":
            return before % 2 == 1 and after % 2 == 1
        return before >= 2 and after >= 2
    m = len(marker)
    return text[max(start - m, 0):start] == marker and text[end:end + m] == marker


def toggle_style(text: str, start: int, end: int, style: str) -> Tuple[str, int, int]:
    """
    Adds or removes a style around text[start:end]. With nothing selected it inserts an empty
    pair to type into. Returns the new text and the new selection.
    """
    marker = STYLE_MARKERS[style]
    m = len(marker)
    if start != end and _is_wrapped(text, start, end, marker):
        return text[:start - m] + text[start:end] + text[end + m:], start - m, end - m
    inner = text[start:end]
    if len(inner) > 2 * m and inner.startswith(marker) and inner.endswith(marker) \
            and _is_wrapped(text, start + m, end - m, marker):
        return text[:start] + inner[m:-m] + text[end:], start, end - 2 * m
    return text[:start] + marker + inner + marker + text[end:], start + m, end + m


def _split_prefixes(line: str) -> Tuple[str, Optional[str], str]:
    """Splits a line into its size, alignment and the rest."""
    size, align, rest = "normal", None, line
    found = True
    while found:
        found = False
        if size == "normal":
            for prefix, value in SIZE_PREFIXES:
                if rest.startswith(prefix):
                    size, rest, found = value, rest[len(prefix):], True
                    break
        if align is None:
            for prefix, value in ALIGN_PREFIXES:
                if rest.startswith(prefix):
                    align, rest, found = value, rest[len(prefix):], True
                    break
    return size, align, rest


def line_style(line: str) -> Tuple[str, Optional[str]]:
    """The size and alignment a line asks for."""
    size, align, _ = _split_prefixes(line)
    return size, align


def set_line_style(line: str, size: Optional[str] = None, align: Optional[str] = "") -> str:
    """
    Rewrites a line's prefixes. size: "large", "medium", "normal", "small", or None to keep it.
    align: "left", "center", "right", None for the label's alignment, or "" to keep it.
    """
    old_size, old_align, rest = _split_prefixes(line)
    size = old_size if size is None else size
    align = old_align if align == "" else align
    out = ""
    if size != "normal":
        out += next(p for p, v in SIZE_PREFIXES if v == size)
    if align is not None:
        out += next(p for p, v in ALIGN_PREFIXES if v == align)
    return out + rest
