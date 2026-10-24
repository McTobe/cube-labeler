#!/usr/bin/env python3
"""
Turns any picture into a black-and-white icon for the label printer.

Shared by importing a picture, making an icon with Gemini and editing an icon later:
the original picture and the settings below are kept with the user's icon, so the same
steps can be run again with other settings. Plain PIL only, so the web version can reuse it.
"""

from collections import deque
from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, Optional, Tuple

from PIL import Image, ImageFilter, ImageOps

# Ways of reading the picture
DRAWING = "drawing"        # dark parts become ink, as drawn
SILHOUETTE = "silhouette"  # like drawing, with every enclosed gap filled: a solid shape
OUTLINE = "outline"        # the edges of a photo become lines
MODES = (DRAWING, SILHOUETTE, OUTLINE)

# Saved icons are this many pixels square
ICON_SIZE = 256
# Space around the ink inside the icon, as a share of the icon size
ICON_PADDING = 0.08
# Originals are kept at most this big
ORIGINAL_MAX = 1024
# Touch-ups are drawn on a grid of this many cells across, close to the printed dots
TOUCH_GRID = 64
TOUCH_NONE, TOUCH_INK, TOUCH_ERASE = 0, 1, 2
# A bin label icon on 12 mm tape is about this many dots high (see icon_manager.PRINT_PREVIEW_DOTS)
PRINT_DOTS = 56
# Ink patches smaller than this many printed dots are taken as specks
SPECK_DOTS = 1.5
# Outline mode looks for edges on a copy this big
OUTLINE_WORK = 480


@dataclass
class IconEdit:
    """Everything that turns an original picture into the icon."""

    mode: str = DRAWING
    threshold: Optional[int] = None  # darkness cutoff 1-254; None picks one from the picture
    invert: bool = False             # swap black and white
    crop: Optional[Tuple[float, float, float, float]] = None  # left, top, right, bottom as 0-1 shares
    rotate: int = 0                  # quarter turns clockwise, 0-3
    flip: bool = False               # mirror left to right
    thickness: int = 0               # printed dots added to lines (negative thins them)
    remove_specks: bool = True
    fill_holes: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["crop"] = list(self.crop) if self.crop else None
        return data

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "IconEdit":
        """Reads saved settings, keeping defaults for anything missing or broken."""
        edit = cls()
        if not isinstance(data, dict):
            return edit
        names = {f.name for f in fields(cls)}
        for key, value in data.items():
            if key in names:
                setattr(edit, key, value)
        try:
            edit.mode = edit.mode if edit.mode in MODES else DRAWING
            edit.threshold = None if edit.threshold is None else min(254, max(1, int(edit.threshold)))
            edit.invert = bool(edit.invert)
            edit.crop = normalise_crop(edit.crop)
            edit.rotate = int(edit.rotate) % 4
            edit.flip = bool(edit.flip)
            edit.thickness = min(4, max(-2, int(edit.thickness)))
            edit.remove_specks = bool(edit.remove_specks)
            edit.fill_holes = bool(edit.fill_holes)
        except (TypeError, ValueError):
            return cls()
        return edit


def normalise_crop(crop) -> Optional[Tuple[float, float, float, float]]:
    """A crop box as sorted 0-1 shares, or None when it is missing or too small to use."""
    try:
        x0, y0, x1, y1 = (min(1.0, max(0.0, float(v))) for v in crop)
    except (TypeError, ValueError):
        return None
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    if x1 - x0 < 0.02 or y1 - y0 < 0.02:
        return None
    if (x0, y0, x1, y1) == (0.0, 0.0, 1.0, 1.0):
        return None
    return (x0, y0, x1, y1)


def prepare_original(image: Image.Image) -> Image.Image:
    """The picture as it is kept with an icon: RGBA, at most ORIGINAL_MAX pixels across."""
    img = image.convert("RGBA")
    img.thumbnail((ORIGINAL_MAX, ORIGINAL_MAX), Image.Resampling.LANCZOS)
    return img


def orient(image: Image.Image, edit: IconEdit) -> Image.Image:
    """Turns and mirrors the picture. Crop shares refer to the picture after this."""
    img = image
    if edit.flip:
        img = ImageOps.mirror(img)
    if edit.rotate:
        img = img.rotate(-90 * edit.rotate, expand=True)
    return img


def crop_box(size: Tuple[int, int], crop) -> Tuple[int, int, int, int]:
    """Crop shares as a pixel box for a picture of `size`."""
    w, h = size
    crop = normalise_crop(crop)
    if not crop:
        return (0, 0, w, h)
    x0, y0, x1, y1 = crop
    box = (int(round(x0 * w)), int(round(y0 * h)), int(round(x1 * w)), int(round(y1 * h)))
    return (box[0], box[1], max(box[2], box[0] + 1), max(box[3], box[1] + 1))


def on_white(image: Image.Image) -> Image.Image:
    """Grayscale picture with any transparency shown as white."""
    rgba = image.convert("RGBA")
    flat = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    flat.alpha_composite(rgba)
    return flat.convert("L")


def border_is_dark(gray: Image.Image) -> bool:
    """True when most of the picture's edge is dark, such as white lines on a black background."""
    w, h = gray.size
    px = gray.load()
    step_x = max(1, w // 64)
    step_y = max(1, h // 64)
    values = [px[x, 0] for x in range(0, w, step_x)] + [px[x, h - 1] for x in range(0, w, step_x)]
    values += [px[0, y] for y in range(0, h, step_y)] + [px[w - 1, y] for y in range(0, h, step_y)]
    values.sort()
    return values[len(values) // 2] < 128


def auto_threshold(gray: Image.Image) -> int:
    """Darkness cutoff that best splits the picture into ink and background (Otsu's method)."""
    hist = gray.histogram()[:256]
    total = sum(hist)
    if not total:
        return 128
    sum_all = sum(i * n for i, n in enumerate(hist))
    sum_bg = 0.0
    weight_bg = 0
    best, best_t = -1.0, 128
    for t in range(256):
        weight_bg += hist[t]
        if not weight_bg:
            continue
        weight_fg = total - weight_bg
        if not weight_fg:
            break
        sum_bg += t * hist[t]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_all - sum_bg) / weight_fg
        between = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if between > best:
            best, best_t = between, t
    # Ink is everything darker than the cutoff, so step just past the split point
    return min(254, max(1, best_t + 1))


def edge_picture(gray: Image.Image) -> Image.Image:
    """Edges of a photo as dark lines on white."""
    small = gray.copy()
    small.thumbnail((OUTLINE_WORK, OUTLINE_WORK), Image.Resampling.LANCZOS)
    edges = small.filter(ImageFilter.GaussianBlur(radius=1.2)).filter(ImageFilter.FIND_EDGES)
    # FIND_EDGES leaves a bright rim along the picture's border
    edges = edges.crop((1, 1, edges.width - 1, edges.height - 1))
    edges = ImageOps.autocontrast(edges, cutoff=1)
    return ImageOps.invert(edges)


def normalised_gray(source: Image.Image, edit: IconEdit) -> Image.Image:
    """The cropped picture in grayscale with ink dark and background light."""
    img = orient(source, edit)
    img = img.crop(crop_box(img.size, edit.crop))
    gray = on_white(img)
    if edit.mode == OUTLINE:
        gray = edge_picture(gray)
    elif border_is_dark(gray):
        gray = ImageOps.invert(gray)
    if edit.invert:
        gray = ImageOps.invert(gray)
    return gray


def threshold_for(source: Image.Image, edit: IconEdit) -> int:
    """The darkness cutoff these settings use: the chosen one, or the automatic one."""
    if edit.threshold is not None:
        return edit.threshold
    return auto_threshold(normalised_gray(source, edit))


def _cut(gray: Image.Image, threshold: int) -> Image.Image:
    """Ink mask: 255 where the picture is darker than the cutoff."""
    return gray.point(lambda v: 255 if v < threshold else 0)


def _odd(n: float) -> int:
    k = max(1, int(round(n)))
    return k if k % 2 else k + 1


def change_thickness(mask: Image.Image, dots: int, dot_px: float) -> Image.Image:
    """Grows (or shrinks, for negative dots) every line by about `dots` printed dots."""
    if not dots:
        return mask
    size = _odd(abs(dots) * dot_px + 1)
    if size < 3:
        size = 3
    filt = ImageFilter.MaxFilter(size) if dots > 0 else ImageFilter.MinFilter(size)
    return mask.filter(filt)


def fill_enclosed(mask: Image.Image) -> Image.Image:
    """Fills every gap the ink fully surrounds, turning outlines into solid shapes."""
    w, h = mask.size
    padded = Image.new("L", (w + 2, h + 2), 0)
    padded.paste(mask, (1, 1))
    data = bytearray(padded.tobytes())
    pw = w + 2
    # Everything not ink that is reachable from the border is background
    outside = bytearray(len(data))
    queue = deque([0])
    outside[0] = 1
    while queue:
        i = queue.popleft()
        x = i % pw
        for j in (i - pw, i + pw, i - 1 if x else -1, i + 1 if x < pw - 1 else -1):
            if 0 <= j < len(data) and not outside[j] and data[j] < 128:
                outside[j] = 1
                queue.append(j)
    filled = bytes(0 if outside[i] else 255 for i in range(len(data)))
    return Image.frombytes("L", (pw, h + 2), filled).crop((1, 1, w + 1, h + 1))


def drop_specks(mask: Image.Image, min_area: int) -> Image.Image:
    """Removes ink patches smaller than `min_area` pixels, such as dust and JPEG noise."""
    if min_area <= 1:
        return mask
    w, h = mask.size
    data = bytearray(mask.tobytes())
    seen = bytearray(len(data))
    for start in range(len(data)):
        if data[start] < 128 or seen[start]:
            continue
        patch = [start]
        seen[start] = 1
        k = 0
        while k < len(patch):
            i = patch[k]
            k += 1
            x = i % w
            for j in (i - w, i + w, i - 1 if x else -1, i + 1 if x < w - 1 else -1):
                if 0 <= j < len(data) and not seen[j] and data[j] >= 128:
                    seen[j] = 1
                    patch.append(j)
        if len(patch) < min_area:
            for i in patch:
                data[i] = 0
    return Image.frombytes("L", (w, h), bytes(data))


def ink_mask(source: Image.Image, edit: IconEdit) -> Image.Image:
    """
    The icon before touch-ups, as an ICON_SIZE square "L" mask with 255 for ink.
    The ink is cropped to its own edges and centred, like the label renderer does.
    """
    gray = normalised_gray(source, edit)
    threshold = edit.threshold if edit.threshold is not None else auto_threshold(gray)
    bbox = _cut(gray, threshold).getbbox()
    if bbox:
        gray = gray.crop(bbox)

    pad = int(ICON_SIZE * ICON_PADDING)
    avail = ICON_SIZE - 2 * pad
    scale = min(avail / gray.width, avail / gray.height)
    new_w = max(1, int(round(gray.width * scale)))
    new_h = max(1, int(round(gray.height * scale)))
    fitted = gray.resize((new_w, new_h), Image.Resampling.LANCZOS)
    mask = Image.new("L", (ICON_SIZE, ICON_SIZE), 0)
    if bbox:
        mask.paste(_cut(fitted, threshold), ((ICON_SIZE - new_w) // 2, (ICON_SIZE - new_h) // 2))

    # One printed dot in icon pixels: the ink's longer side ends up about PRINT_DOTS dots
    dot_px = max(new_w, new_h) / PRINT_DOTS
    if edit.mode == SILHOUETTE or edit.fill_holes:
        mask = fill_enclosed(mask)
    if edit.remove_specks:
        mask = drop_specks(mask, int(round((SPECK_DOTS * dot_px) ** 2)))
    return change_thickness(mask, edit.thickness, dot_px)


def new_touch_layer() -> Image.Image:
    return Image.new("L", (TOUCH_GRID, TOUCH_GRID), TOUCH_NONE)


def apply_touch(mask: Image.Image, touch: Optional[Image.Image]) -> Image.Image:
    """Adds the pencil and eraser cells on top of an ink mask."""
    if touch is None or not touch.getbbox():
        return mask
    big = touch.convert("L").resize(mask.size, Image.Resampling.NEAREST)
    out = mask.copy()
    out.paste(255, mask=big.point(lambda v: 255 if v == TOUCH_INK else 0))
    out.paste(0, mask=big.point(lambda v: 255 if v == TOUCH_ERASE else 0))
    return out


def mask_to_icon(mask: Image.Image) -> Image.Image:
    """Black ink on a see-through background, the way icons are saved."""
    icon = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    icon.paste((0, 0, 0, 255), mask=mask)
    return icon


def render_icon(source: Image.Image, edit: IconEdit, touch: Optional[Image.Image] = None) -> Image.Image:
    """The finished icon for a picture, its settings and touch-ups."""
    return mask_to_icon(apply_touch(ink_mask(source, edit), touch))


def icon_to_mask(icon: Image.Image) -> Image.Image:
    """Ink mask of a finished icon, for opening it again when no original was kept."""
    return ImageOps.invert(on_white(icon)).point(lambda v: 255 if v > 127 else 0)


def print_dots(image: Image.Image, dots: int = PRINT_DOTS, threshold: int = 100) -> Image.Image:
    """
    The icon as it comes out on tape: cropped to its ink, shrunk to `dots` and cut to
    black and white. White is 255, ink is 0.
    """
    gray = on_white(image)
    bbox = gray.point(lambda v: 255 if v < 240 else 0).getbbox()
    if bbox:
        gray = gray.crop(bbox)
    gray.thumbnail((dots, dots), Image.Resampling.LANCZOS)
    return gray.point(lambda v: 255 if v > threshold else 0)


def has_ink(mask: Image.Image) -> bool:
    return mask.getbbox() is not None
