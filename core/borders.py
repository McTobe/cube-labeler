"""
Borders drawn round a text label: our own designs, drawn in code at the printer's resolution.

A border is drawn on its own mask, as big as the label's printable band, and the renderer
keeps the label's content inside the border's insets. Every design is drawn four times as big
and then reduced to printer dots, so curves come out smooth on the 180 dpi head.

The list is data: a new border is a function and one line in BORDERS.
"""
import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFilter

SS = 4  # drawn this many times bigger, then reduced to printer dots
CLEAR_GAP = 0.03  # room between a border and the text, as a share of the printable height

CATEGORIES = [
    ("simple", "Simple"),
    ("pattern", "Patterned"),
    ("lines", "Lines"),
    ("shapes", "Shapes"),
    ("corners", "Corners"),
]
# Themed borders (motifs at the ends) are drawn below but left out of the list for now:
# Tobe wants another look at them first. Add ("themed", "Themed") back and THEMED_BORDERS
# to BORDERS_LIST to bring them back.


class Pen:
    """
    Draws on a canvas SS times as big as the printer dots. Designs are measured in dots of the
    PT-P300BT's 180 dpi head; scale is how many of the printer's dots that is, so a printer
    with a finer head gets the same border, as sharp as it can print it.
    """

    def __init__(self, w: int, h: int, scale: float = 1.0):
        self.px_w, self.px_h = w, h
        self.w, self.h = w / scale, h / scale  # in design dots
        self.k = SS * scale  # canvas pixels per design dot
        self.img = Image.new("L", (w * SS, h * SS), 0)
        self.d = ImageDraw.Draw(self.img)

    def _p(self, pts):
        return [(x * self.k, y * self.k) for x, y in pts]

    def line(self, pts, width=2.0):
        self.d.line(self._p(pts), fill=255, width=max(1, int(round(width * self.k))), joint="curve")

    def poly(self, pts, fill=True, width=2.0):
        if fill:
            self.d.polygon(self._p(pts), fill=255)
        else:
            self.line(list(pts) + [pts[0]], width)

    def rect(self, x0, y0, x1, y1, fill=True, width=2.0, radius=0.0):
        box = [x0 * self.k, y0 * self.k, x1 * self.k - 1, y1 * self.k - 1]
        if fill:
            self.d.rounded_rectangle(box, radius=radius * self.k, fill=255)
        else:
            self.d.rounded_rectangle(box, radius=radius * self.k, outline=255, width=max(1, int(round(width * self.k))))

    def clear_rect(self, x0, y0, x1, y1, radius=0.0):
        self.d.rounded_rectangle([x0 * self.k, y0 * self.k, x1 * self.k - 1, y1 * self.k - 1], radius=radius * self.k, fill=0)

    def circle(self, cx, cy, r, fill=True, width=2.0):
        box = [(cx - r) * self.k, (cy - r) * self.k, (cx + r) * self.k, (cy + r) * self.k]
        if fill:
            self.d.ellipse(box, fill=255)
        else:
            self.d.ellipse(box, outline=255, width=max(1, int(round(width * self.k))))

    def clear_circle(self, cx, cy, r):
        self.d.ellipse([(cx - r) * self.k, (cy - r) * self.k, (cx + r) * self.k, (cy + r) * self.k], fill=0)

    def ellipse(self, cx, cy, rx, ry, angle=0.0, fill=True):
        pts = []
        a = math.radians(angle)
        for i in range(36):
            t = 2 * math.pi * i / 36
            x, y = rx * math.cos(t), ry * math.sin(t)
            pts.append((cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)))
        self.poly(pts, fill=fill)

    def arc(self, cx, cy, r, start, end, width=2.0):
        box = [(cx - r) * self.k, (cy - r) * self.k, (cx + r) * self.k, (cy + r) * self.k]
        self.d.arc(box, start, end, fill=255, width=max(1, int(round(width * self.k))))

    def mask(self) -> Image.Image:
        """The drawing in printer dots, 255 where the printer prints."""
        small = self.img.resize((self.px_w, self.px_h), Image.LANCZOS)
        return small.point(lambda v: 255 if v >= 110 else 0)


def outline_of(shape: Image.Image, width: int) -> Image.Image:
    """The edge of a filled shape mask, width dots thick, on the inside."""
    # Padded with blank, so a shape that touches the edge still gets an edge there
    w, h = shape.size
    padded = Image.new("L", (w + 2 * width, h + 2 * width), 0)
    padded.paste(shape, (width, width))
    inner = padded.filter(ImageFilter.MinFilter(2 * width + 1)).crop((width, width, width + w, width + h))
    return Image.composite(Image.new("L", shape.size, 0), shape, inner)


@dataclass
class Border:
    id: str
    name: str
    category: str
    draw: Callable[[Pen], None]
    # Room kept free for the content, as parts of the printable height
    inset_x: float
    inset_y: float
    # Filled shapes are traced to an outline this thick after drawing (0 = drawn as is)
    trace: int = 0

    def insets(self, h: int) -> Tuple[int, int]:
        if self.id == "none":
            return 0, 0
        # A little clear room on top of the border's own size, so text never touches it
        gap = h * CLEAR_GAP
        return int(round(self.inset_x * h + 2 * gap)), int(round(self.inset_y * h + gap))


# --- Helpers ------------------------------------------------------------------------------

def _along(length: float, step: float) -> List[float]:
    """Evenly spaced centres along an edge, about step apart, starting and ending half a step in."""
    n = max(1, int(round(length / step)))
    real = length / n
    return [real * (i + 0.5) for i in range(n)]


def _edges(p: Pen, inset: float):
    """Each edge as (x0, y0, x1, y1) along the middle of a band inset dots in."""
    w, h = p.w, p.h
    return [
        (inset, inset, w - inset, inset),
        (w - inset, inset, w - inset, h - inset),
        (w - inset, h - inset, inset, h - inset),
        (inset, h - inset, inset, inset),
    ]


def _wave_edge(p: Pen, x0, y0, x1, y1, amp, period, kind, width=1.5):
    """A zigzag, wave or scallop along one edge, swinging amp dots to each side."""
    length = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    nx, ny = -uy, ux
    n = max(2, int(round(length / period)))
    real = length / n
    pts = []
    steps = n * (2 if kind == "zigzag" else 12)
    for i in range(steps + 1):
        t = i / steps * length
        phase = t / real
        if kind == "zigzag":
            off = amp if i % 2 else -amp
        elif kind == "scallop":
            off = -amp + 2 * amp * abs(math.sin(math.pi * phase))
        else:
            off = amp * math.sin(2 * math.pi * phase)
        pts.append((x0 + ux * t + nx * off, y0 + uy * t + ny * off))
    p.line(pts, width)


def _all_edges(p: Pen, inset, fn):
    for e in _edges(p, inset):
        fn(*e)


def _band_dots(p: Pen, inset, step, r, square=False):
    for x0, y0, x1, y1 in _edges(p, inset):
        length = math.hypot(x1 - x0, y1 - y0)
        for t in _along(length, step):
            x = x0 + (x1 - x0) * t / length
            y = y0 + (y1 - y0) * t / length
            if square:
                p.rect(x - r, y - r, x + r, y + r)
            else:
                p.circle(x, y, r)


def _top_bottom(p: Pen, fn, inset):
    fn(0, inset, p.w, inset)
    fn(0, p.h - inset, p.w, p.h - inset)


# --- Simple -------------------------------------------------------------------------------

def _thin(p): p.rect(0, 0, p.w, p.h, fill=False, width=2)
def _thick(p): p.rect(0, 0, p.w, p.h, fill=False, width=4)
def _rounded(p): p.rect(0, 0, p.w, p.h, fill=False, width=2, radius=p.h / 4)
def _rounded_thick(p): p.rect(0, 0, p.w, p.h, fill=False, width=4, radius=p.h / 4)


def _double(p):
    p.rect(0, 0, p.w, p.h, fill=False, width=1.5)
    p.rect(4, 4, p.w - 4, p.h - 4, fill=False, width=1.5)


def _thick_thin(p):
    p.rect(0, 0, p.w, p.h, fill=False, width=3.5)
    p.rect(6, 6, p.w - 6, p.h - 6, fill=False, width=1.2)


def _dotted(p): _band_dots(p, 1.6, 4.5, 1.25)
def _dashed(p):
    for x0, y0, x1, y1 in _edges(p, 1.2):
        length = math.hypot(x1 - x0, y1 - y0)
        for t in _along(length, 9):
            a, b = t - 2.8, t + 2.8
            ux, uy = (x1 - x0) / length, (y1 - y0) / length
            p.line([(x0 + ux * a, y0 + uy * a), (x0 + ux * b, y0 + uy * b)], 2.4)


# --- Patterned ----------------------------------------------------------------------------

def _zigzag(p): _all_edges(p, 2.5, lambda *e: _wave_edge(p, *e, 1.8, 4.5, "zigzag"))
def _wave(p): _all_edges(p, 2.5, lambda *e: _wave_edge(p, *e, 1.8, 8, "wave"))
def _scallop(p): _all_edges(p, 2.5, lambda *e: _wave_edge(p, *e, 1.9, 6, "scallop"))


def _checker(p):
    s = 2.5
    for x0, y0, x1, y1 in _edges(p, s):
        length = math.hypot(x1 - x0, y1 - y0)
        n = int(length // s)
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        for i in range(n):
            for row in (0, 1):
                if (i + row) % 2:
                    continue
                cx = x0 + ux * (i + 0.5) * s
                cy = y0 + uy * (i + 0.5) * s
                off = (row - 0.5) * s
                cx, cy = cx - uy * off, cy + ux * off
                p.rect(cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2)


def _stitch(p):
    p.rect(0, 0, p.w, p.h, fill=False, width=1)
    for x0, y0, x1, y1 in _edges(p, 4.2):
        length = math.hypot(x1 - x0, y1 - y0)
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        for t in _along(length, 5):
            cx, cy = x0 + ux * t, y0 + uy * t
            r = 1.6
            p.line([(cx - r, cy - r), (cx + r, cy + r)], 1.1)
            p.line([(cx - r, cy + r), (cx + r, cy - r)], 1.1)


def _beads(p):
    _band_dots(p, 2.2, 5, 2.0)
    p.rect(5.5, 5.5, p.w - 5.5, p.h - 5.5, fill=False, width=1)


def _rope(p):
    p.rect(0, 0, p.w, p.h, fill=False, width=1)
    p.rect(5, 5, p.w - 5, p.h - 5, fill=False, width=1)
    for x0, y0, x1, y1 in _edges(p, 2.5):
        length = math.hypot(x1 - x0, y1 - y0)
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        nx, ny = -uy, ux
        for t in _along(length, 3.2):
            cx, cy = x0 + ux * t, y0 + uy * t
            p.line([(cx - ux * 1.5 - nx * 2, cy - uy * 1.5 - ny * 2), (cx + ux * 1.5 + nx * 2, cy + uy * 1.5 + ny * 2)], 1.1)


def _ruler(p):
    p.rect(0, 0, p.w, p.h, fill=False, width=1.5)
    for x0, y0, x1, y1 in _edges(p, 0):
        length = math.hypot(x1 - x0, y1 - y0)
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        nx, ny = -uy, ux
        for i, t in enumerate(_along(length, 3.5)):
            tick = 4.5 if i % 4 == 0 else 2.5
            cx, cy = x0 + ux * t, y0 + uy * t
            p.line([(cx, cy), (cx + nx * tick, cy + ny * tick)], 1)


# --- Lines (top and bottom only) ----------------------------------------------------------

def _lines_double(p):
    for y in (0.75, 4, p.h - 4, p.h - 0.75):
        p.line([(0, y), (p.w, y)], 1.5)


def _lines_wave(p): _top_bottom(p, lambda *e: _wave_edge(p, *e, 1.8, 8, "wave", 1.8), 2.4)
def _lines_zigzag(p): _top_bottom(p, lambda *e: _wave_edge(p, *e, 2, 5, "zigzag", 1.6), 2.4)


def _lines_dots(p):
    for y in (2, p.h - 2):
        for x in _along(p.w, 6):
            p.rect(x - 1.6, y - 1.6, x + 1.6, y + 1.6)


def _lines_diamonds(p):
    for y in (2.6, p.h - 2.6):
        p.line([(0, y), (p.w, y)], 1)
        for x in _along(p.w, 7):
            p.poly([(x - 2.6, y), (x, y - 2.6), (x + 2.6, y), (x, y + 2.6)])


def _lines_hatch(p):
    for top in (0, p.h - 5):
        p.line([(0, top + 0.5), (p.w, top + 0.5)], 1)
        p.line([(0, top + 4.5), (p.w, top + 4.5)], 1)
        for x in _along(p.w, 3):
            p.line([(x - 1.5, top + 4.5), (x + 1.5, top + 0.5)], 1)


def _lines_thick(p):
    p.rect(0, 0, p.w, 3.5)
    p.rect(0, p.h - 3.5, p.w, p.h)


def _lines_dashed(p):
    for y in (1.5, p.h - 1.5):
        for x in _along(p.w, 8):
            p.line([(x - 2.6, y), (x + 2.6, y)], 2.6)


# --- Shapes (filled, then traced to an outline) -------------------------------------------

def _tag(p):
    d = p.h * 0.32
    p.poly([(d, 0), (p.w - d, 0), (p.w, p.h / 2), (p.w - d, p.h), (d, p.h), (0, p.h / 2)])


def _ticket(p):
    r = p.h * 0.2
    p.rect(0, 0, p.w, p.h)
    for cx, cy in ((0, 0), (p.w, 0), (0, p.h), (p.w, p.h)):
        p.clear_circle(cx, cy, r)


def _banner(p):
    d = p.h * 0.3
    p.poly([(0, 0), (p.w, 0), (p.w - d, p.h / 2), (p.w, p.h), (0, p.h), (d, p.h / 2)])


def _capsule(p): p.rect(0, 0, p.w, p.h, radius=p.h / 2)


def _plaque(p):
    r = p.h * 0.22
    p.rect(0, 0, p.w, p.h)
    for cx, cy in ((0, 0), (p.w, 0), (0, p.h), (p.w, p.h)):
        p.clear_circle(cx, cy, r)
    # A rounded inner step at each corner, like a name plate
    for cx, cy in ((0, 0), (p.w, 0), (0, p.h), (p.w, p.h)):
        p.clear_rect(cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55)


def _arrow(p):
    d = p.h * 0.45
    p.poly([(0, 0), (p.w - d, 0), (p.w, p.h / 2), (p.w - d, p.h), (0, p.h)])


def _arrow_left(p):
    d = p.h * 0.45
    p.poly([(d, 0), (p.w, 0), (p.w, p.h), (d, p.h), (0, p.h / 2)])


def _flag(p):
    d = p.h * 0.3
    p.poly([(0, 0), (p.w, 0), (p.w - d, p.h / 2), (p.w, p.h), (0, p.h)])


def _flag_left(p):
    d = p.h * 0.3
    p.poly([(0, 0), (p.w, 0), (p.w, p.h), (0, p.h), (d, p.h / 2)])


def _parentheses(p):
    # A round bracket at each end, as tall as the tape
    r = p.h * 0.75
    a = math.degrees(math.asin(min(1.0, (p.h / 2 - 1.5) / r)))
    p.arc(r + 1.5, p.h / 2, r, 180 - a, 180 + a, 3)
    p.arc(p.w - r - 1.5, p.h / 2, r, -a, a, 3)


def _octagon(p):
    c = p.h * 0.28
    p.poly([(c, 0), (p.w - c, 0), (p.w, c), (p.w, p.h - c), (p.w - c, p.h), (c, p.h), (0, p.h - c), (0, c)])


def _brackets(p):
    a = p.h * 0.16
    for side in (0, 1):
        x = 0 if side == 0 else p.w
        s = 1 if side == 0 else -1
        p.line([(x + s * a, 1.5), (x + s * 1.5, 1.5), (x + s * 1.5, p.h - 1.5), (x + s * a, p.h - 1.5)], 3)


# --- Corners ------------------------------------------------------------------------------

def _corner_marks(p):
    a = p.h * 0.32
    w, h = p.w, p.h
    for (x, y, sx, sy) in ((1.5, 1.5, 1, 1), (w - 1.5, 1.5, -1, 1), (1.5, h - 1.5, 1, -1), (w - 1.5, h - 1.5, -1, -1)):
        p.line([(x, y + sy * a), (x, y), (x + sx * a, y)], 3)


def _corner_triangles(p):
    a = p.h * 0.3
    w, h = p.w, p.h
    p.rect(0, 0, w, h, fill=False, width=1)
    for (x, y, sx, sy) in ((0, 0, 1, 1), (w, 0, -1, 1), (0, h, 1, -1), (w, h, -1, -1)):
        p.poly([(x, y), (x + sx * a, y), (x, y + sy * a)])


def _corner_squares(p):
    s = p.h * 0.14
    w, h = p.w, p.h
    p.rect(s / 2, s / 2, w - s / 2, h - s / 2, fill=False, width=1.2)
    for (x, y) in ((0, 0), (w - s, 0), (0, h - s), (w - s, h - s)):
        p.rect(x, y, x + s, y + s)


def _corner_dots(p):
    r = p.h * 0.09
    w, h = p.w, p.h
    p.rect(r, r, w - r, h - r, fill=False, width=1.2)
    for (x, y) in ((r, r), (w - r, r), (r, h - r), (w - r, h - r)):
        p.circle(x, y, r)
        p.clear_circle(x, y, r * 0.4)


def _corner_steps(p):
    w, h = p.w, p.h
    st = p.h * 0.1
    p.rect(st * 2.2, st * 2.2, w - st * 2.2, h - st * 2.2, fill=False, width=1)
    for (x, y, sx, sy) in ((0.8, 0.8, 1, 1), (w - 0.8, 0.8, -1, 1), (0.8, h - 0.8, 1, -1), (w - 0.8, h - 0.8, -1, -1)):
        pts = [(x, y + sy * 3 * st), (x, y), (x + sx * 3 * st, y)]
        p.line(pts, 1.6)
        p.line([(x + sx * st, y + sy * 3 * st), (x + sx * st, y + sy * st), (x + sx * 3 * st, y + sy * st)], 1.6)


def _corner_diamonds(p):
    w, h = p.w, p.h
    a = p.h * 0.13
    p.rect(a, a, w - a, h - a, fill=False, width=1)
    p.rect(a + 3, a + 3, w - a - 3, h - a - 3, fill=False, width=1)
    for (x, y) in ((a, a), (w - a, a), (a, h - a), (w - a, h - a)):
        p.poly([(x - a, y), (x, y - a), (x + a, y), (x, y + a)])


def _corner_curls(p):
    w, h = p.w, p.h
    r = p.h * 0.17
    p.rect(r, 0.6, w - r, 1.8)
    p.rect(r, h - 1.8, w - r, h - 0.6)
    p.rect(0.6, r, 1.8, h - r)
    p.rect(w - 1.8, r, w - 0.6, h - r)
    # A curl turning inwards at each corner
    for (cx, cy, start) in ((r, r, 180), (w - r, r, 270), (w - r, h - r, 0), (r, h - r, 90)):
        p.arc(cx, cy, r - 1.2, start, start + 270, 1.4)
        p.circle(cx, cy, r * 0.28)


def _corner_dot_fill(p):
    w, h = p.w, p.h
    p.rect(0, 0, w, h, fill=False, width=1)
    step = 3.2
    n = 4
    for (x, y, sx, sy) in ((0, 0, 1, 1), (w, 0, -1, 1), (0, h, 1, -1), (w, h, -1, -1)):
        for i in range(n):
            for j in range(n - i):
                p.circle(x + sx * (2.4 + i * step), y + sy * (2.4 + j * step), 0.95)


# --- Themed motifs, each drawn in a square box (x, y, size) --------------------------------

def _star(p, x, y, s, points=5):
    cx, cy, ro, ri = x + s / 2, y + s / 2 + s * 0.04, s / 2, s * 0.2
    pts = []
    for i in range(points * 2):
        a = -math.pi / 2 + i * math.pi / points
        r = ro if i % 2 == 0 else ri
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    p.poly(pts)


def _heart(p, x, y, s):
    r = s * 0.26
    p.circle(x + s * 0.28, y + s * 0.32, r)
    p.circle(x + s * 0.72, y + s * 0.32, r)
    p.poly([(x + s * 0.04, y + s * 0.42), (x + s * 0.96, y + s * 0.42), (x + s * 0.5, y + s * 0.95)])


def _flower(p, x, y, s):
    cx, cy = x + s / 2, y + s / 2
    for i in range(5):
        a = -math.pi / 2 + i * 2 * math.pi / 5
        p.circle(cx + math.cos(a) * s * 0.26, cy + math.sin(a) * s * 0.26, s * 0.2)
    p.clear_circle(cx, cy, s * 0.13)
    p.circle(cx, cy, s * 0.07)


def _leaf(p, x, y, s, angle=-35):
    a = math.radians(angle)
    cx, cy, L, Wd = x + s / 2, y + s / 2, s * 0.5, s * 0.24
    pts = []
    for i in range(25):
        t = -1 + 2 * i / 24
        pts.append((t * L, Wd * (1 - t * t) * (1 - 0.25 * t)))
    for i in range(25):
        t = 1 - 2 * i / 24
        pts.append((t * L, -Wd * (1 - t * t) * (1 - 0.25 * t)))
    p.poly([(cx + u * math.cos(a) - v * math.sin(a), cy + u * math.sin(a) + v * math.cos(a)) for u, v in pts])
    p.d.line([((x + s / 2 - math.cos(a) * s * 0.4) * p.k, (y + s / 2 - math.sin(a) * s * 0.4) * p.k),
              ((x + s / 2 + math.cos(a) * s * 0.4) * p.k, (y + s / 2 + math.sin(a) * s * 0.4) * p.k)], fill=0, width=max(1, round(p.k)))


def _snowflake(p, x, y, s):
    cx, cy = x + s / 2, y + s / 2
    for i in range(6):
        a = i * math.pi / 3
        ex, ey = cx + math.cos(a) * s * 0.48, cy + math.sin(a) * s * 0.48
        p.line([(cx, cy), (ex, ey)], s * 0.08)
        for k in (0.6,):
            bx, by = cx + math.cos(a) * s * 0.48 * k, cy + math.sin(a) * s * 0.48 * k
            for da in (-0.7, 0.7):
                p.line([(bx, by), (bx + math.cos(a + da) * s * 0.16, by + math.sin(a + da) * s * 0.16)], s * 0.07)


def _note(p, x, y, s):
    p.ellipse(x + s * 0.3, y + s * 0.8, s * 0.2, s * 0.14, -20)
    p.ellipse(x + s * 0.78, y + s * 0.68, s * 0.2, s * 0.14, -20)
    p.line([(x + s * 0.47, y + s * 0.78), (x + s * 0.47, y + s * 0.12)], s * 0.08)
    p.line([(x + s * 0.95, y + s * 0.66), (x + s * 0.95, y + s * 0.02)], s * 0.08)
    p.poly([(x + s * 0.43, y + s * 0.1), (x + s * 0.99, y - s * 0.02), (x + s * 0.99, y + s * 0.16), (x + s * 0.43, y + s * 0.28)])


def _wrench(p, x, y, s):
    # Handle from bottom left to top right, open jaw at the top
    p.line([(x + s * 0.18, y + s * 0.85), (x + s * 0.68, y + s * 0.35)], s * 0.17)
    p.circle(x + s * 0.72, y + s * 0.28, s * 0.26)
    p.clear_rect(x + s * 0.68, y - s * 0.05, x + s * 0.9, y + s * 0.26)
    p.circle(x + s * 0.18, y + s * 0.85, s * 0.12)
    p.clear_circle(x + s * 0.18, y + s * 0.85, s * 0.05)


def _screwdriver(p, x, y, s):
    # Lying from top right (handle) to bottom left (tip), like the wrench
    a = math.radians(135)
    def at(u, v):
        return (x + s / 2 + u * math.cos(a) - v * math.sin(a), y + s / 2 + u * math.sin(a) + v * math.cos(a))
    hw = s * 0.15
    p.poly([at(-0.5 * s, -hw), at(-0.05 * s, -hw * 1.1), at(-0.05 * s, hw * 1.1), at(-0.5 * s, hw)])
    p.circle(*at(-0.5 * s, 0), hw)
    p.line([at(-0.05 * s, 0), at(0.4 * s, 0)], s * 0.1)
    p.poly([at(0.38 * s, -s * 0.07), at(0.52 * s, -s * 0.03), at(0.52 * s, s * 0.03), at(0.38 * s, s * 0.07)])


def _bolt(p, x, y, s):
    p.poly([(x + s * 0.6, y), (x + s * 0.15, y + s * 0.58), (x + s * 0.45, y + s * 0.58),
            (x + s * 0.32, y + s), (x + s * 0.85, y + s * 0.38), (x + s * 0.55, y + s * 0.38), (x + s * 0.72, y)])


def _fork(p, x, y, s):
    for k in (0.36, 0.5, 0.64):
        p.line([(x + s * k, y), (x + s * k, y + s * 0.3)], s * 0.07)
    p.rect(x + s * 0.32, y + s * 0.25, x + s * 0.68, y + s * 0.38, radius=s * 0.06)
    p.line([(x + s * 0.5, y + s * 0.35), (x + s * 0.5, y + s * 0.98)], s * 0.11)


def _knife(p, x, y, s):
    p.poly([(x + s * 0.44, y + s * 0.55), (x + s * 0.44, y + s * 0.1), (x + s * 0.52, y), (x + s * 0.62, y + s * 0.2), (x + s * 0.6, y + s * 0.55)])
    p.rect(x + s * 0.42, y + s * 0.55, x + s * 0.62, y + s, radius=s * 0.08)


def _house(p, x, y, s):
    p.poly([(x + s * 0.5, y + s * 0.05), (x + s * 0.98, y + s * 0.48), (x + s * 0.02, y + s * 0.48)])
    p.rect(x + s * 0.14, y + s * 0.46, x + s * 0.86, y + s * 0.98)
    p.clear_rect(x + s * 0.42, y + s * 0.66, x + s * 0.58, y + s * 0.98)
    p.rect(x + s * 0.7, y + s * 0.12, x + s * 0.82, y + s * 0.36)


def _paw(p, x, y, s):
    p.ellipse(x + s * 0.5, y + s * 0.7, s * 0.24, s * 0.2)
    for cx, cy in ((0.2, 0.42), (0.38, 0.2), (0.62, 0.2), (0.8, 0.42)):
        p.ellipse(x + s * cx, y + s * cy, s * 0.1, s * 0.13)


def _sun(p, x, y, s):
    cx, cy = x + s / 2, y + s / 2
    p.circle(cx, cy, s * 0.24)
    for i in range(8):
        a = i * math.pi / 4
        p.line([(cx + math.cos(a) * s * 0.34, cy + math.sin(a) * s * 0.34), (cx + math.cos(a) * s * 0.49, cy + math.sin(a) * s * 0.49)], s * 0.08)


def _cloud(p, x, y, s):
    p.circle(x + s * 0.3, y + s * 0.6, s * 0.2)
    p.circle(x + s * 0.55, y + s * 0.45, s * 0.27)
    p.circle(x + s * 0.78, y + s * 0.62, s * 0.18)
    p.rect(x + s * 0.12, y + s * 0.6, x + s * 0.92, y + s * 0.8, radius=s * 0.1)


def _themed(left, right=None, lines=True, small=None):
    """Motifs at both ends (a smaller second one beside each when small is given) with thin lines between."""
    right = right or left

    def draw(p: Pen):
        s = p.h * 0.62
        y = (p.h - s) / 2
        left(p, 0.5, y, s)
        right(p, p.w - s - 0.5, y, s)
        if small:
            ss = p.h * 0.32
            small(p, s + 0.5, p.h - ss - 1, ss)
            small(p, p.w - s - ss - 0.5, 1, ss)
        if lines:
            x0 = s + (p.h * 0.36 if small else 2)
            x1 = p.w - s - (p.h * 0.36 if small else 2)
            if x1 > x0:
                p.line([(x0, 1.2), (x1, 1.2)], 1.6)
                p.line([(x0, p.h - 1.2), (x1, p.h - 1.2)], 1.6)
    return draw


BORDERS_LIST = [
    Border("none", "None", "simple", lambda p: None, 0, 0),
    Border("box", "Thin", "simple", _thin, 0.08, 0.08),
    Border("thick", "Thick", "simple", _thick, 0.11, 0.11),
    Border("rounded", "Rounded", "simple", _rounded, 0.2, 0.08),
    Border("rounded-thick", "Rounded thick", "simple", _rounded_thick, 0.22, 0.11),
    Border("double", "Double", "simple", _double, 0.14, 0.14),
    Border("thick-thin", "Thick and thin", "simple", _thick_thin, 0.16, 0.16),
    Border("dotted", "Dotted", "simple", _dotted, 0.09, 0.09),
    Border("dashed", "Dashed", "simple", _dashed, 0.09, 0.09),

    Border("zigzag", "Zigzag", "pattern", _zigzag, 0.13, 0.13),
    Border("wave", "Wave", "pattern", _wave, 0.13, 0.13),
    Border("scallop", "Scallop", "pattern", _scallop, 0.13, 0.13),
    Border("checker", "Checker", "pattern", _checker, 0.13, 0.13),
    Border("stitch", "Cross stitch", "pattern", _stitch, 0.16, 0.16),
    Border("beads", "Beads", "pattern", _beads, 0.15, 0.15),
    Border("rope", "Rope", "pattern", _rope, 0.14, 0.14),
    Border("ruler", "Ruler", "pattern", _ruler, 0.13, 0.13),

    Border("lines-double", "Double lines", "lines", _lines_double, 0.02, 0.12),
    Border("lines-wave", "Wavy lines", "lines", _lines_wave, 0.02, 0.12),
    Border("lines-zigzag", "Zigzag lines", "lines", _lines_zigzag, 0.02, 0.12),
    Border("lines-dots", "Square dots", "lines", _lines_dots, 0.02, 0.1),
    Border("lines-diamonds", "Diamonds", "lines", _lines_diamonds, 0.02, 0.13),
    Border("lines-hatch", "Hatched", "lines", _lines_hatch, 0.02, 0.12),
    Border("lines-thick", "Thick lines", "lines", _lines_thick, 0.02, 0.1),
    Border("lines-dashed", "Dashed lines", "lines", _lines_dashed, 0.02, 0.1),

    Border("tag", "Tag", "shapes", _tag, 0.36, 0.08, trace=2),
    Border("ticket", "Ticket", "shapes", _ticket, 0.24, 0.08, trace=2),
    Border("banner", "Banner", "shapes", _banner, 0.36, 0.08, trace=2),
    Border("capsule", "Capsule", "shapes", _capsule, 0.32, 0.08, trace=2),
    Border("plaque", "Plaque", "shapes", _plaque, 0.24, 0.08, trace=2),
    Border("arrow", "Arrow right", "shapes", _arrow, 0.46, 0.08, trace=2),
    Border("arrow-left", "Arrow left", "shapes", _arrow_left, 0.46, 0.08, trace=2),
    Border("flag", "Flag right", "shapes", _flag, 0.32, 0.08, trace=2),
    Border("flag-left", "Flag left", "shapes", _flag_left, 0.32, 0.08, trace=2),
    Border("octagon", "Octagon", "shapes", _octagon, 0.24, 0.08, trace=2),
    Border("brackets", "Brackets", "shapes", _brackets, 0.14, 0.06),
    Border("parentheses", "Round brackets", "shapes", _parentheses, 0.2, 0.06),

    Border("corner-marks", "Corner marks", "corners", _corner_marks, 0.1, 0.1),
    Border("corner-triangles", "Triangles", "corners", _corner_triangles, 0.32, 0.08),
    Border("corner-squares", "Squares", "corners", _corner_squares, 0.14, 0.12),
    Border("corner-dots", "Rings", "corners", _corner_dots, 0.16, 0.12),
    Border("corner-steps", "Steps", "corners", _corner_steps, 0.26, 0.25),
    Border("corner-diamonds", "Diamonds", "corners", _corner_diamonds, 0.24, 0.22),
    Border("corner-curls", "Curls", "corners", _corner_curls, 0.36, 0.08),
    Border("corner-dot-fill", "Dot corners", "corners", _corner_dot_fill, 0.2, 0.08),

]

THEMED_BORDERS = [
    Border("stars", "Stars", "themed", _themed(_star, small=_star), 1.1, 0.07),
    Border("hearts", "Hearts", "themed", _themed(_heart), 0.72, 0.07),
    Border("flowers", "Flowers", "themed", _themed(_flower, small=_flower), 1.1, 0.07),
    Border("leaves", "Leaves", "themed", _themed(lambda p, x, y, s: _leaf(p, x, y, s, -40), lambda p, x, y, s: _leaf(p, x, y, s, 40)), 0.72, 0.07),
    Border("snow", "Snowflakes", "themed", _themed(_snowflake), 0.72, 0.07),
    Border("music", "Music", "themed", _themed(_note), 0.72, 0.07),
    Border("tools", "Tools", "themed", _themed(_wrench, _screwdriver), 0.72, 0.07),
    Border("power", "Power", "themed", _themed(_bolt), 0.72, 0.07),
    Border("kitchen", "Kitchen", "themed", _themed(_fork, _knife), 0.72, 0.07),
    Border("home", "Home", "themed", _themed(_house), 0.72, 0.07),
    Border("paws", "Paws", "themed", _themed(_paw, small=_paw), 1.1, 0.07),
    Border("weather", "Sun and cloud", "themed", _themed(_sun, _cloud), 0.72, 0.07),
]

BORDERS: Dict[str, Border] = {b.id: b for b in BORDERS_LIST}
_DRAWABLE: Dict[str, Border] = {b.id: b for b in BORDERS_LIST + THEMED_BORDERS}


def get(border_id: str) -> Border:
    return BORDERS.get(border_id or "none", BORDERS["none"])


def render(border_id: str, w: int, h: int, scale: float = 1.0) -> Image.Image:
    """
    The border as a mask w x h printer dots, 255 where it prints. scale: printer dots per
    180 dpi dot, for a printer with a finer head.
    """
    b = _DRAWABLE.get(border_id or "none", BORDERS["none"])
    p = Pen(max(w, 4), max(h, 4), scale)
    b.draw(p)
    m = p.mask()
    if b.trace:
        m = outline_of(m, max(1, int(round(b.trace * scale))))
    return m


def catalogue() -> List[dict]:
    """The borders for the picker, in order, with their category."""
    return [{"id": b.id, "name": b.name, "category": b.category} for b in BORDERS_LIST]
