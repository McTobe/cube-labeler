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
    ("themed", "Themed"),
]


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


# --- More motifs for the themed borders, each drawn from a base line or in a box -----------

def _tree(p, x, base, h, w=None):
    """A fir tree standing on base, x in the middle."""
    w = w or h * 0.6
    for top, bottom, wide in ((0, 0.45, 0.55), (0.25, 0.72, 0.8), (0.5, 0.92, 1.0)):
        p.poly([(x, base - h + top * h), (x - wide * w / 2, base - h + bottom * h), (x + wide * w / 2, base - h + bottom * h)])
    p.rect(x - w * 0.08, base - h * 0.1, x + w * 0.08, base)


def _round_tree(p, x, base, h):
    p.rect(x - h * 0.06, base - h * 0.45, x + h * 0.06, base)
    p.circle(x, base - h * 0.62, h * 0.3)
    p.circle(x - h * 0.18, base - h * 0.5, h * 0.2)
    p.circle(x + h * 0.18, base - h * 0.5, h * 0.2)


def _stem_flower(p, x, base, h, r):
    p.line([(x, base), (x, base - h + r)], 1.4)
    _leaf(p, x - r * 1.2, base - h * 0.45 - r * 0.6, r * 1.4, 30)
    _flower(p, x - r, base - h - r * 0.2, 2 * r)


def _tulip(p, x, base, h, r):
    p.line([(x, base), (x, base - h + r)], 1.4)
    _leaf(p, x, base - h * 0.4 - r * 0.6, r * 1.4, -30)
    cx, cy = x, base - h
    p.poly([(cx - r, cy - r * 0.9), (cx - r * 0.4, cy - r * 0.3), (cx, cy - r), (cx + r * 0.4, cy - r * 0.3),
            (cx + r, cy - r * 0.9), (cx + r * 0.9, cy + r * 0.2), (cx, cy + r * 0.8), (cx - r * 0.9, cy + r * 0.2)])


def _grass(p, x, base, h):
    for dx, tall, lean in ((0, 1, -0.3), (2.2, 0.75, 0.4), (-2.2, 0.6, -0.6), (4, 0.5, 0.7)):
        p.poly([(x + dx - 1, base), (x + dx + 1, base), (x + dx + lean * h * tall, base - h * tall)])


def _moon(p, cx, cy, r):
    p.circle(cx, cy, r)
    p.clear_circle(cx + r * 0.45, cy - r * 0.25, r * 0.85)


def _hammer(p, x, y, s):
    p.rect(x + s * 0.44, y + s * 0.25, x + s * 0.56, y + s, radius=s * 0.04)
    p.rect(x + s * 0.15, y + s * 0.05, x + s * 0.85, y + s * 0.3, radius=s * 0.03)
    p.clear_rect(x + s * 0.72, y + s * 0.05, x + s * 0.85, y + s * 0.15)


def _mug(p, x, base, s):
    """A mug with steam, standing on base."""
    p.rect(x, base - s * 0.6, x + s * 0.6, base, radius=s * 0.08)
    p.arc(x + s * 0.62, base - s * 0.32, s * 0.16, 270, 90, s * 0.08)
    for dx in (0.18, 0.42):
        pts = [(x + s * dx + math.sin(t / 3) * s * 0.06, base - s * 0.7 - t * s * 0.05) for t in range(7)]
        p.line(pts, 1.1)


def _pot(p, x, base, s):
    """A cooking pot with a lid, standing on base."""
    p.rect(x, base - s * 0.5, x + s, base, radius=s * 0.06)
    p.rect(x - s * 0.12, base - s * 0.44, x + s * 1.12, base - s * 0.36)
    p.rect(x + s * 0.05, base - s * 0.62, x + s * 0.95, base - s * 0.54, radius=s * 0.04)
    p.circle(x + s * 0.5, base - s * 0.68, s * 0.07)


def _spoon_whisk(p, x, y, s):
    """A spoon and a whisk hanging side by side from y."""
    p.line([(x + s * 0.2, y), (x + s * 0.2, y + s * 0.65)], s * 0.08)
    p.ellipse(x + s * 0.2, y + s * 0.8, s * 0.12, s * 0.2)
    p.line([(x + s * 0.65, y), (x + s * 0.65, y + s * 0.45)], s * 0.08)
    for k in (-0.14, 0, 0.14):
        p.ellipse(x + s * 0.65, y + s * 0.72, abs(k) * s + s * 0.04, s * 0.28, fill=False)


def _waves(p, x0, x1, y, amp=1.6, period=8.0, width=1.4):
    pts = [(x, y + amp * math.sin(2 * math.pi * x / period)) for x in [x0 + i * 0.5 for i in range(int((x1 - x0) * 2) + 1)]]
    p.line(pts, width)


def _boat(p, x, base, s):
    p.poly([(x, base - s * 0.25), (x + s, base - s * 0.25), (x + s * 0.82, base), (x + s * 0.18, base)])
    p.line([(x + s * 0.5, base - s * 0.25), (x + s * 0.5, base - s)], 1.2)
    p.poly([(x + s * 0.55, base - s * 0.95), (x + s * 0.55, base - s * 0.32), (x + s * 0.95, base - s * 0.32)])


def _palm(p, x, base, h):
    pts = [(x + math.sin(t / 6) * h * 0.12, base - t / 10 * h * 0.8) for t in range(11)]
    p.line(pts, h * 0.07)
    tx, ty = pts[-1]
    for ang in (-160, -120, -60, -20, 200):
        a = math.radians(ang)
        _leaf(p, tx + math.cos(a) * h * 0.2 - h * 0.18, ty + math.sin(a) * h * 0.14 - h * 0.08, h * 0.36, ang)


def _plug(p, x, y, s):
    """A mains plug pointing right, its cable leaving on the left."""
    p.rect(x, y + s * 0.2, x + s * 0.6, y + s * 0.8, radius=s * 0.12)
    p.rect(x + s * 0.6, y + s * 0.32, x + s * 0.95, y + s * 0.4)
    p.rect(x + s * 0.6, y + s * 0.6, x + s * 0.95, y + s * 0.68)


def _bulb(p, x, y, s):
    p.circle(x + s * 0.5, y + s * 0.38, s * 0.34)
    p.rect(x + s * 0.32, y + s * 0.62, x + s * 0.68, y + s * 0.92, radius=s * 0.04)
    for k in (0.72, 0.82):
        p.d.line([((x + s * 0.32) * p.k, (y + s * k) * p.k), ((x + s * 0.68) * p.k, (y + s * k) * p.k)], fill=0, width=max(1, round(p.k)))
    for ang in (-150, -110, -70, -30):
        a = math.radians(ang)
        cx, cy = x + s * 0.5, y + s * 0.38
        p.line([(cx + math.cos(a) * s * 0.45, cy + math.sin(a) * s * 0.45), (cx + math.cos(a) * s * 0.6, cy + math.sin(a) * s * 0.6)], 1)


# --- Themed borders: little scenes ---------------------------------------------------------

def _scene_garden(p):
    w, h = p.w, p.h
    base = h - 1.2
    p.line([(0, base), (w, base)], 1.8)
    _stem_flower(p, 10, base, h * 0.8, h * 0.17)
    _tulip(p, 24, base, h * 0.55, h * 0.13)
    _grass(p, 33, base, h * 0.3)
    _tulip(p, w - 11, base, h * 0.8, h * 0.15)
    _stem_flower(p, w - 26, base, h * 0.55, h * 0.14)
    _grass(p, w - 36, base, h * 0.28)
    p.line([(40, 1.2), (w - 40, 1.2)], 1.2)


def _scene_winter(p):
    w, h = p.w, p.h
    base = h - 1.2
    hill = [(x, base - (h * 0.45) * max(0.0, 1 - x / 40) ** 2) for x in range(0, 41, 2)]
    p.line(hill + [(w, base)], 1.8)
    _tree(p, 8, h * 0.62, h * 0.55)
    _tree(p, 20, h * 0.82, h * 0.45)
    _tree(p, w - 9, base, h * 0.8)
    _tree(p, w - 21, base, h * 0.55)
    _moon(p, w - 34, h * 0.22, h * 0.11)
    for x, y in ((30, 6), (w - 46, 10), (36, 14)):
        _star(p, x, y, 4)
    p.line([(30, 1.2), (w - 48, 1.2)], 1.2)


def _scene_workshop(p):
    w, h = p.w, p.h
    rail = 3.5
    p.rect(0, 0.5, w, rail)
    for x in _along(w, 6):
        p.clear_circle(x, 2, 0.7)
    s = h * 0.55
    _wrench(p, 2, rail + 2, s)
    _hammer(p, 2 + s * 0.9, rail + 2, s * 0.75)
    _screwdriver(p, w - s - 2, rail + 2, s)
    p.line([(0, h - 1.5), (w, h - 1.5)], 2.2)


def _scene_night(p):
    w, h = p.w, p.h
    _moon(p, 8, h * 0.4, h * 0.22)
    _star(p, 17, 3, h * 0.18)
    _star(p, 22, h * 0.55, h * 0.12)
    _star(p, 13, h * 0.72, h * 0.1)
    _star(p, w - 12, h * 0.15, h * 0.28)
    _star(p, w - 24, h * 0.6, h * 0.14)
    _star(p, w - 8, h * 0.7, h * 0.1)
    p.line([(30, 1.2), (w - 34, 1.2)], 1.2)
    p.line([(28, h - 1.2), (w - 30, h - 1.2)], 1.2)


def _scene_kitchen(p):
    w, h = p.w, p.h
    shelf = h - 1.5
    p.line([(0, shelf), (w, shelf)], 2.2)
    p.line([(0, 1.2), (w, 1.2)], 1.6)
    _pot(p, 3, shelf, h * 0.45)
    _mug(p, 3 + h * 0.6, shelf, h * 0.42)
    _spoon_whisk(p, w - h * 0.62, 2, h * 0.6)


def _scene_beach(p):
    w, h = p.w, p.h
    _waves(p, 0, w, h - 3, 1.5, 9, 1.5)
    _sun(p, 1, 1, h * 0.42)
    _palm(p, 26, h - 3, h * 0.85)
    _boat(p, w - h * 0.6, h - 3.5, h * 0.55)
    p.line([(34, 1.2), (w - h * 0.7, 1.2)], 1.2)


def _scene_town(p):
    w, h = p.w, p.h
    base = h - 1.2
    p.line([(0, base), (w, base)], 1.8)
    _house(p, 1, base - h * 0.62, h * 0.62)
    _round_tree(p, h * 0.85, base, h * 0.55)
    _house(p, w - h * 0.5, base - h * 0.5, h * 0.48)
    _house(p, w - h * 0.95, base - h * 0.42, h * 0.42)
    _cloud(p, w - h * 0.85, -h * 0.02, h * 0.34)
    p.line([(h * 1.2, 1.2), (w - h * 1.15, 1.2)], 1.2)


def _scene_power(p):
    w, h = p.w, p.h
    # A cable runs along the bottom from a plug on the left to a bulb on the right
    s = h * 0.5
    _plug(p, 1, h - s - 0.5, s)
    p.line([(1, h - s / 2 - 0.5), (0, h - s / 2 - 0.5)], 1.6)
    cable = [(s * 0.95 + 1, h - s / 2 - 0.5), (s + 6, h - 2), (w - h * 0.4, h - 2), (w - h * 0.3, h - h * 0.35)]
    p.line(cable, 1.6)
    _bulb(p, w - h * 0.55, 0.5, h * 0.62)
    _bolt(p, s * 0.2, 1, h * 0.36)
    p.line([(s + 4, 1.2), (w - h * 0.75, 1.2)], 1.2)


# --- Themed borders: garlands along the top and bottom -------------------------------------

def _vine_edge(p, y, flip):
    period = 14
    sign = -1 if flip else 1
    pts = [(x, y + sign * 1.6 * math.sin(2 * math.pi * x / period)) for x in [i * 0.5 for i in range(int(p.w * 2) + 1)]]
    p.line(pts, 1.2)
    for i, x in enumerate(_along(p.w, period / 2)):
        up = (i % 2 == 0) ^ flip
        yy = y + sign * 1.6 * math.sin(2 * math.pi * x / period)
        _leaf(p, x - 3.5, yy - (7 if up else -0.5), 7, -35 if up else 35)


def _garland_leaves(p):
    _vine_edge(p, 4.5, False)
    _vine_edge(p, p.h - 4.5, True)


def _garland_bunting(p):
    sag = 3
    n = max(2, int(p.w // 34))
    seg = p.w / n
    for k in range(n):
        x0 = k * seg
        p.line([(x0 + t * seg, 1 + sag * math.sin(math.pi * t)) for t in [i / 20 for i in range(21)]], 1)
        for t in (0.25, 0.5, 0.75):
            x, y = x0 + t * seg, 1 + sag * math.sin(math.pi * t)
            p.poly([(x - 3.6, y), (x + 3.6, y), (x, y + 9)])
    p.line([(0, p.h - 1.2), (p.w, p.h - 1.2)], 1.2)


def _garland_stars(p):
    for y in (4, p.h - 4):
        p.line([(0, y), (p.w, y)], 0.9)
        for i, x in enumerate(_along(p.w, 12)):
            s = 8 if i % 2 == 0 else 5
            _star(p, x - s / 2, y - s / 2 - 0.2, s)


def _garland_hearts(p):
    for y in (3.6, p.h - 3.6):
        p.line([(0, y), (p.w, y)], 0.8)
        for x in _along(p.w, 10):
            _heart(p, x - 3.5, y - 3.5, 7)


# --- Themed borders: a rounded frame broken by a bunch of pictures in two corners ----------

def _corner_bunch(big, small=None, extra=None):
    """big, small and extra draw a picture in a box (p, x, y, size)."""
    small = small or big

    def draw(p: Pen):
        w, h = p.w, p.h
        r = h * 0.18
        gap = h * 0.5
        # The frame, left open at the top left and bottom right where the pictures sit
        p.line([(gap, 1), (w - r, 1)], 1.6)
        p.arc(w - r, r, r - 1, 270, 360, 1.6)
        p.line([(w - 1, r), (w - 1, h - gap)], 1.6)
        p.line([(r, h - 1), (w - gap, h - 1)], 1.6)
        p.arc(r, h - r, r - 1, 90, 180, 1.6)
        p.line([(1, h - r), (1, gap)], 1.6)
        s = h * 0.46
        big(p, 0, 0, s)
        small(p, s * 0.88, h * 0.02, h * 0.24)
        if extra:
            extra(p, 0, s * 0.96, h * 0.24)
        big(p, w - s, h - s, s)
        small(p, w - s - h * 0.3, h - h * 0.26, h * 0.24)
        if extra:
            extra(p, w - h * 0.24, h - s - h * 0.26, h * 0.24)
    return draw


def _leaf_pair(p, x, y, s):
    _leaf(p, x - s * 0.08, y + s * 0.05, s * 0.75, -60)
    _leaf(p, x + s * 0.3, y + s * 0.2, s * 0.75, -10)


THEMED_BORDERS = [
    Border("garden", "Garden", "themed", _scene_garden, 0.7, 0.07),
    Border("winter", "Winter", "themed", _scene_winter, 0.72, 0.07),
    Border("workshop", "Workshop", "themed", _scene_workshop, 0.95, 0.1),
    Border("night", "Night sky", "themed", _scene_night, 0.5, 0.07),
    Border("kitchen", "Kitchen", "themed", _scene_kitchen, 0.92, 0.1),
    Border("beach", "Beach", "themed", _scene_beach, 0.8, 0.07),
    Border("town", "Town", "themed", _scene_town, 1.15, 0.07),
    Border("power", "Power", "themed", _scene_power, 0.74, 0.07),
    Border("leaf-vine", "Leaf vine", "themed", _garland_leaves, 0.03, 0.22),
    Border("bunting", "Bunting", "themed", _garland_bunting, 0.03, 0.2),
    Border("star-chain", "Star chain", "themed", _garland_stars, 0.03, 0.2),
    Border("heart-chain", "Heart chain", "themed", _garland_hearts, 0.03, 0.17),
    Border("flower-corners", "Flower corners", "themed", _corner_bunch(_flower, _flower, lambda p, x, y, s: _leaf(p, x, y, s, 60)), 0.82, 0.08),
    Border("star-corners", "Star corners", "themed", _corner_bunch(_star, _star, _star), 0.82, 0.08),
    Border("heart-corners", "Heart corners", "themed", _corner_bunch(_heart, _heart), 0.82, 0.08),
    Border("leaf-corners", "Leaf corners", "themed", _corner_bunch(_leaf_pair, lambda p, x, y, s: _leaf(p, x, y, s, -30)), 0.82, 0.08),
    Border("music-corners", "Music corners", "themed", _corner_bunch(_note), 0.82, 0.08),
    Border("snow-corners", "Snow corners", "themed", _corner_bunch(_snowflake), 0.82, 0.08),
    Border("paw-corners", "Paw corners", "themed", _corner_bunch(_paw), 0.82, 0.08),
    Border("tool-corners", "Tool corners", "themed", _corner_bunch(_wrench, _bolt), 0.82, 0.08),
]

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
BORDERS_LIST += THEMED_BORDERS

BORDERS: Dict[str, Border] = {b.id: b for b in BORDERS_LIST}


def get(border_id: str) -> Border:
    return BORDERS.get(border_id or "none", BORDERS["none"])


def render(border_id: str, w: int, h: int, scale: float = 1.0) -> Image.Image:
    """
    The border as a mask w x h printer dots, 255 where it prints. scale: printer dots per
    180 dpi dot, for a printer with a finer head.
    """
    b = get(border_id)
    p = Pen(max(w, 4), max(h, 4), scale)
    b.draw(p)
    m = p.mask()
    if b.trace:
        m = outline_of(m, max(1, int(round(b.trace * scale))))
    return m


def catalogue() -> List[dict]:
    """The borders for the picker, in order, with their category."""
    return [{"id": b.id, "name": b.name, "category": b.category} for b in BORDERS_LIST]
