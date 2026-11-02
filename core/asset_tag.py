"""
Asset tags: numbered labels for computers, tools and anything lent out or kept track of.

An asset tag is a text label worked out from a few fields: the tag (a prefix and a number, as
PC-0042) and the owner, one big and one small, with a barcode or QR code beside them. Drawing
it as that text label keeps the renderer's fitting, fonts and codes in one place, and a saved
or queued tag draws the same in the desktop app and the web version.
"""

import dataclasses
import re

# Characters that mean styling in label text (core/rich_text.py), kept as plain text here: the
# inline markers anywhere, and the line markers (# - < > [) at the start of a line
_INLINE = re.compile(r"([\\*_=])")
_LINE_START = "#-<>["
LINK_PLACEHOLDER = "{tag}"


def tag_text(prefix: str, number: str) -> str:
    """The tag as printed, as PC-0042: the prefix and the number as typed."""
    return f"{(prefix or '').strip()}{(number or '').strip()}"


def next_number(number: str, step: int = 1) -> str:
    """
    The number step tags on, keeping its width: 0042 goes to 0043, 0099 to 0100 and 9 to 10.
    Letters in front stay (A7 goes to A8); a number without digits stays as it is.
    """
    match = re.search(r"(\d+)(\D*)$", number or "")
    if not match:
        return number or ""
    digits = match.group(1)
    value = str(int(digits) + step).zfill(len(digits))
    return number[:match.start(1)] + value + match.group(2)


def link_for(link: str, tag: str) -> str:
    """The link with the tag put in for {tag}, or on the end when the link has no {tag}."""
    link = (link or "").strip()
    if not link:
        return ""
    return link.replace(LINK_PLACEHOLDER, tag) if LINK_PLACEHOLDER in link else link + tag


def code_data(config) -> str:
    """What the tag's barcode or QR code holds."""
    tag = tag_text(config.asset_prefix, config.asset_number)
    if config.asset_code_holds == "link":
        return link_for(config.asset_link, tag) or tag
    return tag


def _plain(text: str) -> str:
    text = _INLINE.sub(r"\\\1", text.strip())
    return "\\" + text if text[:1] in _LINE_START and text else text


def as_text_label(config):
    """The text label an asset tag config draws as."""
    tag = tag_text(config.asset_prefix, config.asset_number)
    owner = (config.asset_owner or "").strip()
    big, small = (tag, owner) if config.asset_big != "owner" else (owner, tag)
    lines = []
    if big:
        lines.append(f"# **{_plain(big)}**")
    if small:
        lines.append(_plain(small))
    data = code_data(config)
    code = config.asset_code if data else "none"
    side = "right" if config.asset_code_side == "right" else "left"
    return dataclasses.replace(
        config,
        layout="text",
        text="\n".join(lines),
        qr_enabled=code == "qr",
        qr_data=data if code == "qr" else "",
        qr_position=side,
        barcode_enabled=code == "barcode",
        barcode_data=data if code == "barcode" else "",
        barcode_position=side,
        image_path=None,
    )
