"""
The themed borders: little pictures at the ends of a label, drawn in code at printer resolution.

Each design draws on a borders.Pen through Art, in units of a 12 mm label (64 = the tape
height), so it keeps its proportions on any tape. The pictures are our own drawings: big black
shapes with white details cut out, and a line that joins the two ends of the label.
"""
import math


def bez(p0, p1, p2, p3, n=28):
    out = []
    for i in range(n + 1):
        t = i / n
        a = (1 - t) ** 3; b = 3 * (1 - t) ** 2 * t; c = 3 * (1 - t) * t * t; d = t ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def oval_pts(cx, cy, rx, ry, ang=0, n=48):
    a = math.radians(ang)
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        pts.append((cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)))
    return pts


def box_pts(x0, y0, x1, y1, r=0.0):
    if r <= 0:
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(7):
            a = math.radians(a0 + i * 15)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def heart_pts(cx, cy, s, n=40):
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x * s / 34, cy + y * s / 34))
    return pts


def sparkle_pts(cx, cy, r, inner=0.22):
    pts = []
    for i in range(8):
        a = -math.pi / 2 + i * math.pi / 4
        rr = r if i % 2 == 0 else r * inner
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


class Art:
    """
    Draws on a borders.Pen in units of a 12 mm label, so 64 is the tape height and every
    picture keeps its proportions on any tape. It can move, turn, mirror and scale a picture,
    and "on=False" draws in white, to cut details out of black shapes.
    """

    def __init__(self, p, ox=0.0, oy=0.0, rot=0.0, mirror=False, s=1.0):
        self.p = p
        self.u = p.h / 64.0
        self.s = s
        self.ox, self.oy, self.mirror = ox, oy, mirror
        self.ca, self.sa = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        self.W = p.w / self.u

    def T(self, pts):
        k = self.p.k * self.u
        out = []
        for x, y in pts:
            x, y = x * self.s, y * self.s
            if self.mirror:
                x = -x
            x, y = x * self.ca - y * self.sa, x * self.sa + y * self.ca
            out.append(((x + self.ox) * k, (y + self.oy) * k))
        return out

    def _w(self, w, on=True):
        dots = w * self.s * self.u
        if on:
            dots = max(dots, 0.9)  # on narrow tape a line still prints
        return max(1, int(round(dots * self.p.k)))

    def fill(self, pts, on=True):
        self.p.d.polygon(self.T(pts), fill=255 if on else 0)

    def clear(self, pts):
        self.fill(pts, False)

    def stroke(self, pts, w=1.6, on=True):
        tp = self.T(pts)
        width = self._w(w, on)
        self.p.d.line(tp, fill=255 if on else 0, width=width, joint="curve")
        # round ends
        for x, y in (tp[0], tp[-1]):
            r = width / 2
            self.p.d.ellipse([x - r, y - r, x + r, y + r], fill=255 if on else 0)

    def erase(self, pts, w=1.2):
        self.stroke(pts, w, False)

    def dot(self, cx, cy, r, on=True):
        self.fill(oval_pts(cx, cy, r, r, 0, 24), on)

    def hole(self, cx, cy, r):
        self.dot(cx, cy, r, False)

    def oval(self, cx, cy, rx, ry, ang=0, on=True):
        self.fill(oval_pts(cx, cy, rx, ry, ang), on)

    def ring(self, cx, cy, r, w, on=True):
        pts = oval_pts(cx, cy, r, r, 0, 60)
        self.stroke(pts + [pts[0]], w, on)

    def box(self, x0, y0, x1, y1, r=0.0, on=True):
        self.fill(box_pts(x0, y0, x1, y1, r), on)

    def outline(self, pts, w=1.4):
        self.stroke(list(pts) + [pts[0]], w)

    def dashed(self, pts, w=1.2, dash=3.0, gap=2.0):
        acc, on, cur = 0.0, True, [pts[0]]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            L = math.hypot(x1 - x0, y1 - y0)
            pos = 0.0
            while pos < L:
                left = (dash if on else gap) - acc
                step = min(left, L - pos)
                pos += step; acc += step
                pt = (x0 + (x1 - x0) * pos / L, y0 + (y1 - y0) * pos / L)
                if on:
                    cur.append(pt)
                if acc >= (dash if on else gap) - 1e-9:
                    if on and len(cur) > 1:
                        self.stroke(cur, w)
                    on = not on; acc = 0.0; cur = [pt]
        if on and len(cur) > 1:
            self.stroke(cur, w)

    def dots_along(self, pts, step, r):
        acc = step
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            L = math.hypot(x1 - x0, y1 - y0)
            pos = 0.0
            while pos + (step - acc) <= L:
                pos += step - acc; acc = 0
                self.dot(x0 + (x1 - x0) * pos / L, y0 + (y1 - y0) * pos / L, r)
            acc += L - pos


def curl(a, x0, y, size=7, w=1.6, right=True):
    """A loop in a base line, like a ribbon curling."""
    pts = []
    for i in range(41):
        t = i / 40
        x = x0 + (size * 1.5) * t + size * 0.5 * math.sin(2 * math.pi * t) * (1 if right else -1)
        yy = y - size * 0.55 * (1 - math.cos(2 * math.pi * t))
        pts.append((x, yy))
    a.stroke(pts, w)


def leaf_pts(cx, cy, L, Wd, ang):
    a = math.radians(ang)
    pts = []
    for i in range(25):
        t = -1 + 2 * i / 24
        pts.append((t * L, Wd * (1 - t * t) * (1 - 0.25 * t)))
    for i in range(25):
        t = 1 - 2 * i / 24
        pts.append((t * L, -Wd * (1 - t * t) * (1 - 0.25 * t)))
    return [(cx + u * math.cos(a) - v * math.sin(a), cy + u * math.sin(a) + v * math.cos(a)) for u, v in pts]


def leaf(a, cx, cy, L, Wd, ang, vein=True):
    a.fill(leaf_pts(cx, cy, L, Wd, ang))
    if vein:
        r = math.radians(ang)
        a.erase([(cx - L * 0.6 * math.cos(r), cy - L * 0.6 * math.sin(r)), (cx + L * 0.55 * math.cos(r), cy + L * 0.55 * math.sin(r))], 0.9)


def flower5(a, cx, cy, r, hole=True):
    for i in range(5):
        t = -math.pi / 2 + i * 2 * math.pi / 5
        a.dot(cx + math.cos(t) * r * 0.55, cy + math.sin(t) * r * 0.55, r * 0.45)
    if hole:
        a.hole(cx, cy, r * 0.28)
        a.dot(cx, cy, r * 0.12)


# --- Garden: sunflowers and a beehive -----------------------------------------------------

def sunflower(a, cx, cy, R, petals=12):
    for i in range(petals):
        t = 2 * math.pi * i / petals
        d = R * 0.66
        a.oval(cx + math.cos(t) * d, cy + math.sin(t) * d, R * 0.34, R * 0.15, math.degrees(t))
    a.hole(cx, cy, R * 0.56)
    a.dot(cx, cy, R * 0.48)
    rr = R * 0.4
    s = R * 0.21
    k = -3
    while k <= 3:
        off = k * s
        for sgn in (1, -1):
            # chord of the disc along a 45 degree line
            nx, ny = math.cos(math.radians(45 * sgn)), math.sin(math.radians(45 * sgn))
            px, py = -ny * off, nx * off
            h = rr * rr - off * off
            if h > 0:
                h = math.sqrt(h)
                a.erase([(cx + px - nx * h, cy + py - ny * h), (cx + px + nx * h, cy + py + ny * h)], 0.9)
        k += 1


def bee(p, x, y, s):
    b = Art(p, ox=x, oy=y, s=s)
    b.oval(2.5, -5.5, 2.8, 4.6, 25); b.oval(2.5, -5.5, 1.5, 3.2, 25, on=False)
    b.oval(0, 0, 6.6, 4.8)
    for sx in (-1.6, 1.8):
        b.erase([(sx - 0.6, -6), (sx + 0.6, 6)], 1.2)
    b.fill([(6, -1.2), (9.5, 0), (6, 1.2)])
    b.dot(-8.8, 0.6, 3.4)
    b.hole(-9.6, -0.2, 0.9)
    b.stroke(bez((-9, -3), (-10, -6), (-12, -7), (-13.5, -7.5)), 0.9)
    b.dot(-13.8, -7.6, 1.0)
    b.oval(-1, -6.5, 2.8, 4.6, -10); b.oval(-1, -6.5, 1.5, 3.2, -10, on=False)


def garden(p):
    a = Art(p); W = a.W; B = 62
    a.stroke([(0, B), (W, B)], 2.0)
    # left: two sunflowers, leaves, grass, a curl
    a.stroke(bez((17, 34), (15, 44), (20, 52), (18, B)), 2.6)
    leaf(a, 25.5, 46, 8, 3.4, -32)
    leaf(a, 9.5, 51, 7.5, 3.2, 212)
    sunflower(a, 17, 18, 16.5)
    a.stroke(bez((37, 42), (36, 50), (38, 56), (37, B)), 2.0)
    sunflower(a, 37, 37.5, 8.5, 10)
    for x, hgt, lean in ((2, 7, -2), (5, 9, 1), (28, 6, -1.5), (31, 8, 2), (44, 6, 1.5)):
        a.fill([(x - 1.3, B), (x + lean, B - hgt), (x + 1.3, B)])
    curl(a, 41, B, 8, 1.6)
    # right: a straw beehive with a bee and its dotted path
    cx = W - 16
    for i in range(5):
        y1 = B - i * 6.2; y0 = y1 - 6.2
        half = 14.5 * math.sqrt(max(0.0, 1 - ((i + 0.5) / 5.4) ** 2)) + 1.5
        a.box(cx - half, y0, cx + half, y1, 3)
        if i:
            a.erase([(cx - half - 1, y1), (cx + half + 1, y1)], 1.0)
    a.fill(oval_pts(cx, B, 4.2, 5.6)[24:] + [(cx + 4.2, B)], False)
    a.stroke([(cx - 18, B), (cx + 18, B)], 2.0)
    a.dots_along(bez((W - 27, 19), (W - 20, 30), (W - 42, 32), (W - 34, 50)), 2.8, 0.75)
    bee(p, W - 37, 15, 1.3)


# --- Kitchen: jam jars, a mixing bowl and a cookie -----------------------------------------

def kitchen(p):
    a = Art(p); W = a.W; B = 62
    a.stroke([(0, B), (W, B)], 2.0)
    # big jar with a gingham cloth top and a heart label
    a.box(3, 27, 27, B, 5)
    a.box(6, 22, 24, 28, 1)
    cloth = [(7, 15), (23, 15), (26, 19), (30, 26.5), (27, 25), (24.5, 27.5), (21.5, 25.5), (18.5, 28), (15, 25.5), (11.5, 28), (8.5, 25.5), (5.5, 27.5), (3, 25), (0, 26.5), (4, 19)]
    a.fill(cloth)
    for row, y in enumerate((16.6, 20.6)):
        for x in range(6 + 2 * row, 26, 4):
            a.box(x, y, x + 2, y + 2, 0, on=False)
    a.erase([(3, 24), (27, 24)], 1.0)
    a.box(7.5, 36, 22.5, 54, 2.5, on=False)
    a.fill(heart_pts(15, 45.5, 10))
    # small jar
    a.box(31, 44, 45, B, 3)
    a.box(32, 39, 44, 43.5, 1)
    a.box(34, 49, 42, 56, 1.5, on=False)
    a.fill(sparkle_pts(38, 52.5, 3, 0.3))
    # right: mixing bowl with a whisk and a wooden spoon, a cookie, flour sparkles
    cx = W - 24
    # spoon
    a.stroke([(cx + 2, 36), (cx + 11, 9)], 2.2)
    a.oval(cx + 12.6, 4.6, 3.4, 5.2, 18)
    a.oval(cx + 12.4, 5.2, 1.6, 3.0, 18, on=False)
    # whisk
    a.stroke([(cx - 4, 36), (cx - 9.5, 22)], 2.6)
    ang = math.degrees(math.atan2(-14, -5.5))
    ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    for ry in (1.0, 2.6, 4.2):
        c = (cx - 9.5 + ux * 8, 22 + uy * 8)
        pts = oval_pts(c[0], c[1], 8.5, ry, ang, 40)
        a.stroke(pts + [pts[0]], 0.95)
    bowl = oval_pts(cx, 40, 20, 19.5, 0, 72)[0:37]
    a.fill([(cx + 20, 40)] + bowl + [(cx - 20, 40)])
    a.box(cx - 22, 36.5, cx + 22, 41.5, 2.5)
    a.stroke(oval_pts(cx, 41, 15.5, 13.5, 0, 72)[3:34], 1.2, on=False)
    a.box(cx - 8, B - 3.5, cx + 8, B, 1)
    a.erase([(cx - 21, 41.6), (cx + 21, 41.6)], 0.9)
    a.dot(cx - 32, 55, 7.2)
    for dx, dy in ((-2.5, -2.5), (2, -1.5), (-1, 2.4), (3, 3)):
        a.hole(cx - 32 + dx, 55 + dy, 1.1)
    for x, y, r in ((cx - 30, 30, 3.2), (cx - 36, 41, 2.2), (cx - 22, 18, 1.8)):
        a.fill(sparkle_pts(x, y, r))


# --- Winter: snowy mountains and mittens on a line ------------------------------------------

def tree(a, cx, base, H, trunk=True):
    w = H * 0.42
    for i in range(3):
        top = base - H + i * H * 0.24
        bot = top + H * 0.38
        hw = w * (0.55 + 0.25 * i)
        a.fill([(cx, top), (cx + hw, bot), (cx - hw, bot)])
    if trunk:
        a.box(cx - 1.3, base - H * 0.2, cx + 1.3, base)


def snowflake(a, cx, cy, r, w=1.4):
    for i in range(6):
        t = math.radians(90 + i * 60)
        ux, uy = math.cos(t), math.sin(t)
        a.stroke([(cx, cy), (cx + ux * r, cy + uy * r)], w)
        for side in (1, -1):
            b = t + side * math.radians(45)
            bx, by = cx + ux * r * 0.55, cy + uy * r * 0.55
            a.stroke([(bx, by), (bx + math.cos(b) * r * 0.36, by + math.sin(b) * r * 0.36)], w * 0.8)
    a.dot(cx, cy, w * 1.1)


def sled(a, x, base):
    """A wooden sled on the snow, its runner curling up at the front (on the right)."""
    a.stroke([(x, base - 2)] + [(x + 36 + 5 * math.sin(math.radians(t)), base - 7 + 5 * math.cos(math.radians(t))) for t in range(0, 271, 15)], 1.6)
    for sx in (x + 5, x + 16, x + 27):
        a.stroke([(sx, base - 2), (sx, base - 8)], 1.4)
    a.box(x - 1, base - 11.5, x + 34, base - 7.5, 1)
    for sx in (x + 10.5, x + 22.5):
        a.erase([(sx, base - 11), (sx, base - 8)], 0.9)


def winter(p):
    a = Art(p); W = a.W; B = 62
    back = [(14, B), (38, 22), (60, B)]
    a.fill(back)
    capb = [(38, 22), (32.4, 31.8), (35, 30), (37, 33), (39.5, 29.5), (42, 32.5), (44.3, 33)]
    a.clear(capb); a.outline(capb, 1.5)
    front = [(0, B), (19, 8), (40, B)]
    a.stroke(front + [front[0]], 3.2, on=False)
    a.fill(front)
    cap = [(19, 8), (12.2, 27.5), (15, 25), (17.5, 29.5), (20.5, 25), (23.5, 28.5), (26.1, 27.5)]
    a.clear(cap); a.outline(cap, 1.6)
    # a pine in front, with a little room cut round it
    cx, H = 52, 20
    a.stroke([(cx, B - H - 1), (cx + H * 0.42 + 1, B), (cx - H * 0.42 - 1, B), (cx, B - H - 1)], 2.4, on=False)
    tree(a, cx, B, H)
    a.stroke([(0, B), (W, B)], 2.0)
    for x, y in ((46, 8), (52, 22), (4, 6), (30, 6), (8, 34), (58, 12)):
        a.dot(x, y, 1.1)
    # a sled carrying a little pine, a big snowflake, falling snow
    sled(a, W - 47, B)
    tree(a, W - 30, B - 11.5, 26)
    snowflake(a, W - 9, 12, 8)
    snowflake(a, W - 52, 24, 5.5, 1.2)
    for x, y in ((W - 58, 34), (W - 40, 6), (W - 20, 30), (W - 6, 34), (W - 52, 50), (W - 26, 4)):
        a.dot(x, y, 1.1)


# --- Beach: lighthouse with beams; sailboat, sun and gulls ----------------------------------

def gull(a, x, y, s):
    a.stroke(bez((x - s, y), (x - s * 0.6, y - s * 0.7), (x - s * 0.2, y - s * 0.5), (x, y)), 1.1)
    a.stroke(bez((x, y), (x + s * 0.2, y - s * 0.5), (x + s * 0.6, y - s * 0.7), (x + s, y)), 1.1)


def beach(p):
    a = Art(p); W = a.W; B = 61
    def wave(x0, x1, y, amp=1.2, per=7.0, w=1.4):
        a.stroke([(x, y + amp * math.sin(2 * math.pi * x / per)) for x in [x0 + i * 0.5 for i in range(int((x1 - x0) * 2) + 1)]], w)
    wave(0, W, B)
    # lighthouse
    def xat(y, left=True):
        t = (y - 20) / 38.0
        return (8 - 3 * t) if left else (20 + 3 * t)
    for y0, y1 in ((20, 27), (34, 41), (48, 58)):
        a.fill([(xat(y0), y0), (xat(y0, False), y0), (xat(y1, False), y1), (xat(y1), y1)])
    a.outline([(8, 20), (20, 20), (23, 58), (5, 58)], 1.4)
    a.box(12, 51, 16, 58.5, 2, on=False)
    a.box(5, 17.5, 23, 20.5, 0.6)
    a.outline([(9, 9.5), (19, 9.5), (19, 17.5), (9, 17.5)], 1.3)
    a.dot(14, 13.5, 2.2)
    a.fill([(7.5, 10), (20.5, 10), (14, 3.5)])
    a.dot(14, 3, 1.1)
    for y2 in (5, 13.5, 22):
        a.dashed([(22, 13.5 + (y2 - 13.5) * 0.15), (38, y2)], 1.3, 3.2, 2.2)
    a.oval(4, 59, 6.5, 4); a.oval(24, 59.5, 5, 3)
    gull(a, 34, 30, 3.6); gull(a, 42, 24, 2.6)
    # boat, sun, gulls
    a.fill([(W - 47, 50), (W - 4, 50), (W - 11, 58.5), (W - 40, 58.5)])
    for x in (W - 34, W - 26, W - 18):
        a.hole(x, 54, 1.2)
    a.stroke([(W - 26.5, 50), (W - 26.5, 7)], 1.5)
    a.fill([(W - 26.5, 6), (W - 20, 8), (W - 26.5, 10)])
    a.fill([(W - 24.5, 11), (W - 24.5, 47.5), (W - 6, 47.5)])
    a.erase([(W - 24.5, 30), (W - 15, 30)], 1.0)
    a.fill([(W - 28.5, 13), (W - 28.5, 47.5), (W - 43, 47.5)])
    a.erase([(W - 28.5, 33), (W - 37, 33)], 1.0)
    sx, sy = W - 50, 12
    a.dot(sx, sy, 4.4)
    for i in range(12):
        t = 2 * math.pi * i / 12
        r1 = 6.0; r2 = 8.6 if i % 2 == 0 else 7.4
        a.stroke([(sx + math.cos(t) * r1, sy + math.sin(t) * r1), (sx + math.cos(t) * r2, sy + math.sin(t) * r2)], 1.1)
    gull(a, W - 56, 28, 3.2)


# --- Town: terraced houses and a lamp; bicycle with a flower basket -------------------------

def windows(a, x0, x1, ys, w=3.6, h=4.4):
    n = 2
    gap = (x1 - x0 - n * w) / (n + 1)
    for y in ys:
        for i in range(n):
            x = x0 + gap + i * (w + gap)
            a.box(x, y, x + w, y + h, 0.6, on=False)


def town(p):
    a = Art(p); W = a.W; B = 61.5
    # cobbled street
    x = 0.0
    while x < W:
        a.box(x, B, min(W, x + 5), B + 2.5, 0.9)
        x += 6.2
    # three houses
    a.box(0, 28, 15, B); a.fill([(-1, 29), (7.5, 17), (16, 29)])
    windows(a, 0, 15, (32, 41)); a.box(5.5, 50, 9.5, B, 2, on=False)
    a.box(16.2, 20, 30, B)
    a.fill([(16.2, 23), (18.2, 23), (18.2, 18.5), (20.4, 18.5), (20.4, 13), (25.8, 13), (25.8, 18.5), (28, 18.5), (28, 23), (30, 23), (30, 21), (16.2, 21)])
    a.dot(23.1, 16.3, 1.1, on=False)
    windows(a, 16.2, 30, (25, 33.5, 42))
    a.box(20.5, 51, 25.7, B, 2.6, on=False)
    a.box(31.2, 35, 44, B); a.fill([(30.4, 36), (37.6, 27.5), (44.8, 36)])
    a.box(40, 24, 42.5, 33)
    a.stroke([(41.2, 22), (39.8, 19), (42.5, 16.5), (41, 13.5), (43.5, 11)], 1.0)
    windows(a, 31.2, 44, (39,)); a.box(35, 50, 40, B, 2.4, on=False)
    a.fill([(36, 50), (35, 48.5), (40, 48.5), (39, 50)])
    # lamp post
    a.stroke([(50.5, B), (50.5, 26)], 1.4)
    a.box(48.6, B - 3, 52.4, B)
    a.fill([(47.8, 20), (53.2, 20), (52.2, 27), (48.8, 27)])
    a.box(49.6, 21.5, 51.4, 25.5, 0.4, on=False)
    a.fill([(47, 20), (54, 20), (50.5, 16.5)])
    a.dot(50.5, 15.6, 0.9)
    # bicycle
    R = (W - 45, 51.5); F = (W - 13, 51.5); r = 9.6
    for c in (R, F):
        a.ring(c[0], c[1], r, 1.8)
        for i in range(6):
            t = math.pi * i / 6
            a.stroke([(c[0] - math.cos(t) * r, c[1] - math.sin(t) * r), (c[0] + math.cos(t) * r, c[1] + math.sin(t) * r)], 0.75)
        a.dot(c[0], c[1], 1.5)
    Bb = (W - 31, 51.5); S = (W - 35, 37.5); H = (W - 18.5, 37.5)
    for p0, p1 in ((R, Bb), (R, S), (S, Bb), (S, H), (Bb, H), (H, F)):
        a.stroke([p0, p1], 1.8)
    a.stroke([(S[0], S[1]), (S[0] - 1, S[1] - 3)], 1.6)
    a.oval(S[0] - 1.6, S[1] - 3.6, 3.4, 1.3)
    a.stroke([(H[0], H[1]), (H[0] - 1.2, H[1] - 4), (H[0] - 4.5, H[1] - 4.5)], 1.5)
    a.ring(Bb[0], Bb[1], 2.4, 1.2)
    a.stroke([(Bb[0], Bb[1]), (Bb[0] + 2.4, Bb[1] + 3.6)], 1.3)
    a.box(W - 15.5, 30.5, W - 3.5, 38.5, 1)
    for x in (W - 12.5, W - 9.5, W - 6.5):
        a.erase([(x, 31.6), (x, 37.4)], 0.8)
    a.erase([(W - 15, 34.5), (W - 4, 34.5)], 0.8)
    a.stroke([(W - 9.5, 24), (W - 9.5, 31)], 1.2)
    leaf(a, W - 13, 27.5, 3.2, 1.4, 210, vein=False)
    flower5(a, W - 9.5, 22.5, 5.6)


# --- Space: a rocket whose trail becomes the line; a ringed planet -------------------------

def space(p):
    a = Art(p); W = a.W; B = 62
    trail = bez((9, 47), (2, 54), (6, 62), (22, B))
    a.dashed(trail, 1.6, 2.6, 2.0)
    a.stroke([(24, B), (W, B)], 1.6)
    rk = Art(p, ox=13, oy=44, rot=-42)
    rk.fill([(-1, -3.6), (-13, -0.5), (-9, 0), (-13, 0.5), (-1, 3.6)])
    rk.fill([(-1.5, -1.6), (-7.5, 0), (-1.5, 1.6)], on=False)
    rk.fill([(0, -5.5), (15, -5.5)] + [(15 + 11 * math.sin(math.pi / 2 * i / 10), -5.5 * math.cos(math.pi / 2 * i / 10)) for i in range(11)][1:] +
            [(15 + 11 * math.cos(math.pi / 2 * i / 10), 5.5 * math.sin(math.pi / 2 * i / 10)) for i in range(11)][1:] + [(0, 5.5)])
    rk.fill([(0, -5.5), (-4, -12), (2, -12), (9, -5.5)])
    rk.fill([(0, 5.5), (-4, 12), (2, 12), (9, 5.5)])
    rk.dot(12.5, 0, 3.4, on=False); rk.dot(12.5, 0, 1.9)
    rk.erase([(4, -6), (4, 6)], 1.1)
    rk.erase([(21.5, -4), (21.5, 4)], 1.0)
    for x, y, r in ((4, 8, 3.6), (42, 6, 3.0), (36, 20, 2.0), (45, 30, 3.8), (28, 36, 1.6)):
        a.fill(sparkle_pts(x, y, r))
    for x, y in ((14, 6), (40, 40), (52, 16), (24, 52)):
        a.dot(x, y, 0.9)
    # planet with a ring
    cx, cy, R = W - 24, 29, 13
    a.dot(cx, cy, R)
    for yy in (24, 33.5):
        a.erase([(cx - R, yy), (cx + R, yy)], 1.3)
    ring = oval_pts(cx, cy, 24, 6.5, -14, 90)
    front = ring[0:46]
    a.stroke(front, 4.6, on=False)
    a.stroke(ring + [ring[0]], 1.8)
    a.dot(W - 46, 50, 5.5); a.dot(W - 43.6, 48.3, 4.8, on=False)
    for x, y, r in ((W - 6, 52, 3.4), (W - 50, 12, 2.6), (W - 18, 52, 1.8), (W - 4, 6, 2.2)):
        a.fill(sparkle_pts(x, y, r))
    for x, y in ((W - 40, 56), (W - 30, 50), (W - 48, 30)):
        a.dot(x, y, 0.9)


# --- Music: a guitar with notes; notes on a staff with a final barline ----------------------

def note(a, x, y, s=1.0, kind='q'):
    a.oval(x, y, 2.6 * s, 1.9 * s, -22)
    if kind == 'h':
        a.oval(x, y, 1.5 * s, 0.85 * s, -22, on=False)
    a.stroke([(x + 2.3 * s, y - 0.6 * s), (x + 2.3 * s, y - 12 * s)], 1.2 * s)
    if kind == 'e':
        a.stroke(bez((x + 2.3 * s, y - 12 * s), (x + 3 * s, y - 9 * s), (x + 6.5 * s, y - 8 * s), (x + 5 * s, y - 4 * s)), 1.2 * s)


def beamed(a, x1, y1, x2, y2, s=1.0, top=12):
    a.oval(x1, y1, 2.6 * s, 1.9 * s, -22); a.oval(x2, y2, 2.6 * s, 1.9 * s, -22)
    t1 = (x1 + 2.3 * s, y1 - top * s); t2 = (x2 + 2.3 * s, y2 - top * s)
    a.stroke([(x1 + 2.3 * s, y1 - 0.6 * s), t1], 1.2 * s)
    a.stroke([(x2 + 2.3 * s, y2 - 0.6 * s), t2], 1.2 * s)
    a.stroke([t1, t2], 2.4 * s)


def music(p):
    a = Art(p); W = a.W
    ys = [45, 49, 53, 57, 61]
    if a.u < 0.6:
        ys = [45, 53, 61]  # on narrow tape five lines would run together
    for y in ys[:-1]:
        a.stroke([(0, y), (60, y)], 0.9)
        a.stroke([(W - 60, y), (W, y)], 0.9)
    a.stroke([(0, 61), (W, 61)], 1.4)
    # guitar
    g = Art(p, ox=17, oy=48, rot=33)
    for on, grow in ((False, 2.0), (True, 0.0)):
        g.dot(0, 0, 10.5 + grow, on); g.dot(0, -15, 8 + grow, on); g.box(-6 - grow, -15, 6 + grow, 0, 0, on)
        g.box(-1.8 - grow, -40 - grow, 1.8 + grow, -15, 0, on)
        g.box(-3 - grow, -47 - grow, 3 + grow, -39, 1.4, on)
    g.hole(0, -9, 3.6)
    g.erase([(-4.5, 4), (4.5, 4)], 1.5)
    g.erase([(0, -5), (0, 4)], 0.7)
    for y in (-44.5, -41.5):
        g.dot(-4.4, y, 1.0); g.dot(4.4, y, 1.0)
    note(a, 37, 14, 0.9, 'e')
    beamed(a, 41, 30, 49, 26, 0.85)
    note(a, 8, 12, 0.7, 'q')
    # right: notes on the staff and a final barline
    note(a, W - 54, 55, 1.0, 'q')
    beamed(a, W - 45, 51, W - 37, 47, 1.0)
    note(a, W - 27, 53, 1.0, 'h')
    a.stroke([(W - 10, 45), (W - 10, 61)], 1.0)
    a.box(W - 6.5, 45, W - 3, 61)
    a.dot(W - 14, 51, 1.1); a.dot(W - 14, 55, 1.1)
    note(a, W - 40, 22, 0.9, 'e'); note(a, W - 22, 16, 0.75, 'q')


# --- Party: balloons whose string becomes the line; a birthday cake ------------------------

def balloon(a, cx, cy, rx, ry):
    a.oval(cx, cy, rx + 1.5, ry + 1.5, on=False)
    a.oval(cx, cy, rx, ry)
    a.fill([(cx - 1.8, cy + ry + 1.8), (cx + 1.8, cy + ry + 1.8), (cx, cy + ry - 0.8)])
    a.oval(cx - rx * 0.42, cy - ry * 0.42, rx * 0.16, ry * 0.3, 32, on=False)


def party(p):
    a = Art(p); W = a.W; B = 61.5
    knot = (21, 47)
    a.stroke(bez((9, 33), (7, 40), (16, 42), knot), 0.9)
    a.stroke(bez((27, 30), (29, 38), (22, 41), knot), 0.9)
    a.stroke(bez((17, 42.5), (19, 45), (20, 46), knot), 0.9)
    balloon(a, 9, 21, 7.5, 9.5)
    balloon(a, 27, 18.5, 7, 9)
    balloon(a, 17, 31, 7.8, 9.8)
    a.dot(knot[0], knot[1], 1.2)
    a.stroke(bez(knot, (20, 53), (24, 56), (27, 52)) + bez((27, 52), (30, 47), (24, 45), (24, 50))[1:] + bez((24, 50), (24, 56), (30, B), (38, B))[1:], 1.0)
    a.stroke([(37, B), (W, B)], 1.8)
    # cake
    cx = W - 26
    a.box(cx - 21, 44, cx + 21, B, 2)
    a.erase([(cx - 21 + i * 0.5, 48 + 1.6 * abs(math.sin(math.pi * i * 0.5 / 6))) for i in range(85)], 1.2)
    for x in range(-15, 16, 6):
        a.hole(cx + x, 55, 1.1)
    a.box(cx - 13, 31, cx + 13, 44.6, 2)
    a.erase([(cx - 13 + i * 0.5, 37 + 1.4 * math.sin(math.pi * i * 0.5 / 3)) for i in range(53)], 1.1)
    for x, top in ((-7, 21), (0, 19), (7, 21)):
        a.box(cx + x - 1.4, top, cx + x + 1.4, 31)
        a.erase([(cx + x - 1.4, top + 4), (cx + x + 1.4, top + 2.5)], 0.7)
        a.fill(leaf_pts(cx + x, top - 3.2, 2.6, 1.3, -90))
    a.stroke([(cx - 25, B), (cx + 25, B)], 2.2)
    for x, y, ang in ((W - 54, 12, 20), (W - 44, 6, -30), (W - 6, 10, 40), (W - 12, 24, -10), (W - 52, 32, 60), (W - 2, 36, 10), (W - 36, 14, 70)):
        a.fill([(x + 1.6 * math.cos(math.radians(ang + k)), y + 1.6 * math.sin(math.radians(ang + k))) for k in (30, 150, 210, 330)])
    for x, y in ((W - 48, 20), (W - 20, 8), (W - 30, 4), (W - 58, 44)):
        a.dot(x, y, 1.0)
    a.fill(sparkle_pts(W - 16, 14, 3))


# --- Scroll corners --------------------------------------------------------------------------

def spiral(cx, cy, r0, r1, a0, turns, n=80, cw=True):
    pts = []
    for i in range(n + 1):
        t = i / n
        r = r0 + (r1 - r0) * t
        ang = a0 + (1 if cw else -1) * turns * 2 * math.pi * t
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def scroll_corner(a):
    # the top line curls into a big spiral in the corner; the side line rises into a smaller one
    sp1 = spiral(16, 13, 10, 2.2, math.radians(270), 1.0)
    a.stroke(bez((44, 2.4), (32, 2.4), (24, 2.4), sp1[0]) + sp1[1:], 2.4)
    a.dot(*sp1[-1], 2.1)
    sp2 = spiral(9.5, 33, 7.5, 2.0, math.radians(90), 0.85, cw=True)
    a.stroke(bez((2.4, 54), (2.4, 46), (2.4, 40.5), sp2[0]) + sp2[1:], 2.0)
    a.dot(*sp2[-1], 1.8)
    leaf(a, 31, 7.6, 6.0, 2.6, 22)
    leaf(a, 6.8, 49, 5.2, 2.3, 112)
    a.dot(29, 15, 1.3); a.dot(34, 13.5, 0.9)


def scrolls(p):
    a = Art(p); W = a.W; H = 64
    a.stroke([(44, 2.4), (W - 14, 2.4)], 1.6)
    a.stroke([(14, H - 2.4), (W - 44, H - 2.4)], 1.6)
    corner = [(2.4 + 11.6 - 11.6 * math.cos(math.radians(t)), H - 14 + 11.6 * math.sin(math.radians(t))) for t in range(0, 91, 6)]
    a.stroke([(2.4, 54)] + corner, 1.6)
    a.stroke([(W - x, H - y) for x, y in [(2.4, 54)] + corner], 1.6)
    scroll_corner(a)
    scroll_corner(Art(p, ox=W, oy=H, rot=180))


# --- Bunting: flags strung between two poles -----------------------------------------------

def flag(a, x, y, ang, kind):
    """A pennant hanging from the string at (x, y), turned to follow it; kind picks its pattern."""
    # placed through the parent drawing, which may be mirrored for the right-hand end
    f = Art(a.p, ox=a.ox + (-x if a.mirror else x), oy=a.oy + y, rot=-ang if a.mirror else ang, mirror=a.mirror)
    f.fill([(-4.4, 0), (4.4, 0), (0, 11.0)])
    if kind == 0:  # a white dot
        f.hole(0, 3.6, 1.7)
    elif kind == 1:  # white inside a black edge, with a black dot
        f.clear([(-2.6, 1.3), (2.6, 1.3), (0, 7.6)])
        f.dot(0, 3.2, 0.9)
    elif kind == 2:  # a white star
        f.fill(sparkle_pts(0, 3.8, 2.6, 0.3), on=False)
    else:  # a white heart
        f.fill(heart_pts(0, 3.9, 5.0), on=False)


def bunting(p):
    """Flags strung along the top from pole to pole, in swags, over a line on the ground."""
    a = Art(p); W = a.W; B = 62
    left, right = 3.5, W - 3.5
    top, sag = 4.0, 3.2
    n = max(1, int(round((right - left) / 48)))
    seg = (right - left) / n
    k = 0
    for i in range(n):
        x0 = left + i * seg
        a.stroke([(x0 + t * seg, top + sag * math.sin(math.pi * t)) for t in [j / 30 for j in range(31)]], 1.0)
        m = max(3, int(round(seg / 11)))
        for j in range(m):
            t = (j + 0.5) / m
            ang = math.degrees(math.atan(sag * math.pi * math.cos(math.pi * t) / seg))
            flag(a, x0 + t * seg, top + sag * math.sin(math.pi * t) - 0.4, ang, k % 4)
            k += 1
        if i:
            a.dot(x0, top, 1.4)
    for side in (Art(p), Art(p, ox=W, mirror=True)):
        side.stroke([(3.5, 4), (3.5, B)], 2.0)
        side.dot(3.5, 2.6, 2.4)
        side.box(0.8, B - 2.8, 6.2, B, 0.6)
        for gx, gh, lean in ((8, 4, 1), (10.5, 6, -1), (13, 3.5, 1.5)):
            side.fill([(gx - 1.1, B), (gx + lean, B - gh), (gx + 1.1, B)])
    a.stroke([(0, B), (W, B)], 1.6)


# --- Laurel ends ------------------------------------------------------------------------------

def laurel(a):
    """A laurel branch curving up the end of the label, drawn round its middle at (0, 0)."""
    cx, cy, R = 13, 0, 27
    stem = [(cx + R * math.cos(math.radians(t)), cy + R * math.sin(math.radians(t))) for t in range(128, 237, 3)]
    a.stroke(stem, 1.5)
    for t in range(135, 230, 16):
        r = math.radians(t)
        x, y = cx + R * math.cos(r), cy + R * math.sin(r)
        tang = math.degrees(r) + 90
        for side in (1, -1):
            ang = tang + side * 42
            L = 5.0
            leaf(a, x + math.cos(math.radians(ang)) * L, y + math.sin(math.radians(ang)) * L, 5.4, 2.3, ang)
    tx, ty = cx + R * math.cos(math.radians(238)), cy + R * math.sin(math.radians(238))
    leaf(a, tx + 2.6, ty - 3.2, 4.8, 2.1, 238 + 90 - 10)
    for t in (152, 184, 216):
        r = math.radians(t)
        a.dot(cx + (R - 4.5) * math.cos(r), cy + (R - 4.5) * math.sin(r), 1.3)


def laurels(p):
    a = Art(p); W = a.W
    tilt, down = 7, 1.8
    laurel(Art(p, ox=21, oy=32 + down, rot=-tilt))
    laurel(Art(p, ox=W - 21, oy=32 + down, rot=tilt, mirror=True))
    for y in (3, 61):
        a.stroke([(30, y), (W - 30, y)], 0.9)
    for y in (6, 58):
        a.dots_along([(33, y), (W - 33, y)], 4.0, 0.6)


# --- Deco fans ------------------------------------------------------------------------------

def fan(a):
    R = 23
    for k in range(6):
        t0, t1 = k * 15 + 1.6, (k + 1) * 15 - 1.6
        pts = [(9.5 * math.cos(math.radians(t)), 9.5 * math.sin(math.radians(t))) for t in (t0, t1)]
        outer = [(R * math.cos(math.radians(t0 + (t1 - t0) * i / 6)), R * math.sin(math.radians(t0 + (t1 - t0) * i / 6))) for i in range(7)]
        a.fill([pts[0]] + outer + [pts[1]])
    a.stroke([((R + 2.6) * math.cos(math.radians(t)), (R + 2.6) * math.sin(math.radians(t))) for t in range(0, 91, 3)], 1.0)
    a.dot(0, 0, 6.5)


def deco(p):
    a = Art(p); W = a.W; H = 64
    for inset, w in ((1.2, 1.6), (4.6, 0.9)):
        a.stroke([(30, inset), (W - inset - 8, inset)], w)
        a.stroke([(W - inset, inset + 8), (W - inset, H - 30)], w)
        a.stroke([(W - 30, H - inset), (inset + 8, H - inset)], w)
        a.stroke([(inset, H - inset - 8), (inset, 30)], w)
    for c in (Art(p), Art(p, ox=W, oy=H, rot=180)):
        fan(c)
    for c in (Art(p, ox=W, oy=0, rot=90), Art(p, ox=0, oy=H, rot=-90)):
        c.stroke([(1.2, 9.2), (5, 9.2), (5, 5), (9.2, 5), (9.2, 1.2)], 1.6)
        c.stroke([(4.6, 12.6), (8.4, 12.6), (8.4, 8.4), (12.6, 8.4), (12.6, 4.6)], 0.9)
        c.dot(12.5, 12.5, 1.4)
