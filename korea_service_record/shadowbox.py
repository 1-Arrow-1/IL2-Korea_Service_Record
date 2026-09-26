"""
The shadowbox: a pilot's decorations laid out in a glazed display case.

The case is a photograph of a real wooden box - frame, blue velvet, glass -
and everything else is dropped onto it: medals on their drapes, the aviator
badge, the Air Force seal, the squadron emblem, the unit citations and a
brass plate flanked by the pilot's rank devices.

Positions are worked out here, in the frame's own pixel space, and handed to
the page as percentages. Two reasons for putting the arithmetic on this side
rather than in CSS. The measurements were taken off the reference box in
``docs/reference/usaf_shadowbox_mockup.jpg`` and belong next to the note
saying where they came from; and a layout that is a list of placements can
be rendered to a PNG later without moving any of it.

That reference is kept as a JPEG because the original is a 6MB PNG, so it
shows the intended arrangement but is no longer exact to the pixel. The
constants below, not the picture, are what the layout is built from.

Nothing here is localised. A shadowbox is an object hanging on a wall, and
the engraving on its plate reads the same whatever language the tracker is
set to - so the plate is always English and the rank name comes from the
game's English strings, not the reader's.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import medals as medal_art

logger = logging.getLogger(__name__)

# Bumped whenever a constant below moves, so a cached layout is not drawn
# against a frame it was not measured for.
REVISION = 4

# The frame photograph. Every number below is in its pixel space.
FRAME = (2050, 1860)

# The glass goes on last, over everything. It is stored pre-scaled to the
# size it is placed at, so it only needs an offset; x is not zero because
# the reflection is cropped tighter on the left than the frame is.
GLASS_AT = (53, 0)

# The velvet's horizontal middle, and the one axis everything in the case is
# hung on. Not FRAME[0] / 2: the moulding is a shade wider on the right, and
# rows centred on the true centre of the picture sit visibly off-centre
# inside the box. Every centred piece derives from this rather than carrying
# its own measured x - the reference box was laid out by hand and its badge
# and citation bars ended up 24px right of its seal, patch and plate, which
# is invisible on their own and obvious once they are stacked.
CENTRE_X = 1022

# Medals hang in rows of up to seven. A pilot of the 601st can reach
# fourteen ladders in all - sixteen in awards.cfg less the two that are unit
# citations - so two rows is the whole wall and no third row is possible.
MEDAL_PER_ROW = 7
MEDAL_GAP = 14

# Where the top of the ribbon sits for each row. The medals themselves end
# at wildly different heights - the Medal of Honor hangs almost twice as far
# as the Air Medal - so rows are hung from their ribbons, which is how a real
# case is mounted and the only line that reads as straight.
MEDAL_ROW_TOP = (132, 655)

# The lower shelf: the Air Force seal, the aviator badge and the squadron
# patch. Each is centred on its own point rather than sharing a baseline -
# the badge rides higher because the citation bars are pinned beneath it.
SEAL_AT = (443, 1313)
BADGE_AT = (CENTRE_X, 1226)
PATCH_AT = (1602, 1325)

# The aviator badge is mounted slightly over its atlas size. It is a small
# piece of art beside two 290px discs and reads as an afterthought at 1:1.
BADGE_SCALE = 1.05

# The squadron emblem goes in at its atlas size. The tile is 320 square with
# a 14px clear border, so the emblem itself comes out 289 across - within
# four pixels of the Air Force seal facing it, which is what pairs them.
# Scaling the tile to the seal's canvas instead would shrink the emblem.

# Unit citations, pinned in a line beneath the badge. Their atlas tiles are
# 456 wide and go in at half size, which is exactly the 228 measured off the
# reference box.
CITATION_SCALE = 0.5
CITATION_GAP = 64
CITATION_Y = 1427

# The brass plate, given as the ink itself rather than the canvas - the art
# carries a wide transparent margin and placing the canvas would put the
# plate somewhere else entirely.
PLATE = (CENTRE_X - 739 / 2.0, 1547, 739, 142)

# Rank devices butt against the plate at this distance, at their own size,
# centred on the plate. The widest device in the set is the Major General
# star cluster at 394px, which still clears the moulding on both sides.
RANK_GAP = 68

# The Air Force seal is furniture, not an award, and has no atlas tile.
SEAL_SIZE = (295, 294)

# The neck orders are the one set drawn by hand. Their atlas tiles show the
# Medal of Honor on a short drape like any other medal; in a case it hangs
# from its full neck ribbon, which is a different piece of art.
DRAWN_NECK = (601026, 601041)

# A row is scaled down if it will not fit between the mouldings. It only
# bites on a full row of unusually wide tiles, but a medal drawn over the
# frame is worse than one drawn a few per cent small.
INTERIOR = (140, 1905)

# How the ribbon top is found in a piece of art: the band is the widest the
# art gets in its top quarter, and the ribbon starts at the first row that
# reaches most of it. Neither the canvas nor the ink bounding box will do -
# the tiles carry different amounts of clear space above the ribbon, and
# some have a suspension ring or a clasp poking up above it.
BAND_REGION = 0.25
BAND_REACH = 0.80

# The rank devices on disk, by the game's own rank id with 601 dropped. A
# general's star is symmetrical and ships as one file; everything below it is
# handed and ships as a pair.
RANK_FILES = {0: "6010", 1: "6011", 2: "6012", 3: "6013",
              4: "6014", 5: "6015", 6: "6016", 7: "6017"}
RANK_UNHANDED = {6, 7}

# Rank devices, measured off the files so a placement does not have to open
# them. Keyed the same way as RANK_FILES.
RANK_SIZE = {0: (64, 166), 1: (65, 165), 2: (168, 167), 3: (173, 188),
             4: (173, 188), 5: (296, 161), 6: (185, 184), 7: (394, 196)}

# Only the Air Force is furnished. The Navy, the Marines and the Soviet and
# Korean air forces want their own frame, cloth and devices, and a box built
# out of USAF furniture would be wrong rather than merely plain.
COUNTRIES = (601,)


# Measured art, by award id. The atlas does not change while the tracker is
# running and the answer is three small integers, so it is worked out once.
_GEOMETRY: Dict[int, Tuple[int, int, int]] = {}
_TILES: Dict[str, Tuple[int, int, int]] = {}


def _measure(data: bytes) -> Tuple[int, int, int]:
    """Width, height and ribbon top of one piece of art."""
    import numpy as np
    from PIL import Image

    im = Image.open(io.BytesIO(data)).convert("RGBA")
    opaque = np.asarray(im)[..., 3] > 128
    widths = opaque.sum(axis=1)
    head = widths[:max(4, int(len(widths) * BAND_REGION))]
    band = int(head.max()) if len(head) else 0
    top = int(np.argmax(widths >= BAND_REACH * band)) if band else 0
    return im.width, im.height, top


def _tile(icons, kind: str, ident: str) -> Optional[Tuple[str, int, int, int]]:
    """Source and measurements for one tile of any of the game's sheets."""
    key = f"{kind}:{ident}"
    if key not in _TILES:
        data = icons.png(kind, ident)
        if data is None:
            logger.warning("No %s tile for %s", kind, ident)
            return None
        try:
            _TILES[key] = _measure(data)
        except Exception as exc:                  # pragma: no cover - art only
            logger.warning("Cannot measure %s %s: %s", kind, ident, exc)
            return None
    return (f"/api/icon/{kind}/{ident}",) + _TILES[key]


def _art(icons, award_id: int) -> Optional[Tuple[str, int, int, int]]:
    """
    The source and measurements for one award's full-size art.

    Everything comes from the game's own atlas, at the size the atlas draws
    it, so the case shows the same medals the game does. The neck orders are
    the exception and are read from the files drawn for them.
    """
    if award_id in _GEOMETRY:
        src, = (f"/static/images/shadowbox/601/{award_id}.png",) if award_id in DRAWN_NECK \
            else (f"/api/icon/award/{award_id}",)
        return (src,) + _GEOMETRY[award_id]
    if award_id in DRAWN_NECK:
        path = (Path(__file__).resolve().parent / "static" / "images" /
                "shadowbox" / "601" / f"{award_id}.png")
        if not path.is_file():
            return None
        data, src = path.read_bytes(), f"/static/images/shadowbox/601/{award_id}.png"
    else:
        data = icons.png("award", str(award_id))
        if data is None:
            logger.warning("No atlas tile for award %s", award_id)
            return None
        src = f"/api/icon/award/{award_id}"
    try:
        _GEOMETRY[award_id] = _measure(data)
    except Exception as exc:                      # pragma: no cover - art only
        logger.warning("Cannot measure award %s: %s", award_id, exc)
        return None
    return (src,) + _GEOMETRY[award_id]


def available(country: Optional[int]) -> bool:
    """Whether a box can be built for this pilot's air force."""
    return country in COUNTRIES


def _pct(x: float, y: float, w: float, h: float) -> Dict[str, float]:
    """One placement, as percentages of the frame."""
    return {"left": round(100.0 * x / FRAME[0], 4),
            "top": round(100.0 * y / FRAME[1], 4),
            "width": round(100.0 * w / FRAME[0], 4),
            "height": round(100.0 * h / FRAME[1], 4)}


def _row_tops(rows: int) -> List[float]:
    """
    The ribbon line each row of medals hangs from.

    Two rows take the measured positions. A single row is hung midway
    between them instead of at the top one: the case was laid out around a
    full rack, and a lone row left up at the first line leaves the middle
    of the velvet bare with the shelf stranded far below it.
    """
    if rows <= 1:
        return [(MEDAL_ROW_TOP[0] + MEDAL_ROW_TOP[1]) / 2.0]
    return [float(y) for y in MEDAL_ROW_TOP[:rows]]


def _row_sizes(count: int) -> List[int]:
    """
    How many medals hang in each row, top to bottom.

    ``medals.rows`` puts the short row on top, which is how a rack is worn
    and how the reference box is arranged.
    """
    return medal_art.rows(count, MEDAL_PER_ROW) if count else []


def _place_row(art: Sequence[Tuple[int, int, int]], line: float) -> List[tuple]:
    """
    Lay a row of medals out around ``CENTRE_X``, hung from a common ribbon.

    Every tile is a different size and carries a different amount of clear
    space above its ribbon, so neither a fixed pitch nor a shared top edge
    will do. Each piece is placed by its own ribbon top, which puts all the
    ribbons on ``line`` - the way a case is actually mounted, and the only
    line in a row of medals that reads as straight.
    """
    widths = [w for w, _, _ in art]
    total = sum(widths) + MEDAL_GAP * (len(widths) - 1)
    room = INTERIOR[1] - INTERIOR[0]
    scale = min(1.0, room / total) if total else 1.0
    gap = MEDAL_GAP * scale
    x = CENTRE_X - total * scale / 2.0
    out = []
    for w, h, ribbon in art:
        out.append((x, line - ribbon * scale, w * scale, h * scale))
        x += w * scale + gap
    return out


def _centred(cx: float, cy: float, w: float, h: float) -> tuple:
    return (cx - w / 2.0, cy - h / 2.0, w, h)


def plate_text(rank: str, name: str) -> Dict[str, str]:
    """
    The engraving, in full and abbreviated.

    Both go to the page because only the page knows how wide the text
    actually runs in the font it loaded. It measures the full form, and
    falls back to the initial when the plate cannot hold it.
    """
    full = f"{rank} {name}".strip()
    parts = name.split()
    short = (f"{rank} {parts[0][0]}. {' '.join(parts[1:])}".strip()
             if len(parts) > 1 and parts[0] else full)
    return {"full": full, "short": short}


def layout(rack: Dict[str, Any], rank_id: Optional[int], squadron_key: Optional[str],
           icons, rev: int = 0) -> Dict[str, Any]:
    """
    Every piece in the box, in the order it should be drawn.

    ``rack`` is the tunic payload the detail page already builds - the same
    medals, citations and badge the pilot wears - so the box and the uniform
    can never disagree about what he has been given. ``icons`` is the sheet
    reader the medals and badges are sliced from.
    """
    items: List[Dict[str, Any]] = []

    def add(src: str, box: tuple, name: str = "", cls: str = "") -> None:
        x, y, w, h = box
        items.append({"src": src, "name": name, "cls": cls, **_pct(x, y, w, h)})

    # --- the medals ----------------------------------------------------
    # The neck order is worn at the throat and leads the line; the rest
    # follow in precedence, which is the order the rack already holds them.
    wanted = ([(rack["neck"], rack.get("neck_name") or "")] if rack.get("neck") else [])
    wanted += [(m["type"], m.get("name") or "") for m in rack.get("medals") or []]

    worn: List[Dict[str, Any]] = []
    for award_id, name in wanted:
        art = _art(icons, award_id)
        if art is None:
            continue
        src, w, h, ribbon = art
        worn.append({"name": name, "src": f"{src}?v={rev}", "art": (w, h, ribbon)})

    # A pilot cannot hold more than two rows' worth, but a preview rack can
    # ask for anything; anything past the second row is dropped rather than
    # drawn over the seal.
    sizes = _row_sizes(len(worn))[:len(MEDAL_ROW_TOP)]
    tops = _row_tops(len(sizes))
    placed = 0
    for row_index, count in enumerate(sizes):
        row = worn[placed:placed + count]
        placed += count
        boxes = _place_row([m["art"] for m in row], tops[row_index])
        for medal, box in zip(row, boxes):
            add(medal["src"], box, medal["name"], "sbox-medal")

    # --- the lower shelf ------------------------------------------------
    add(f"/static/images/shadowbox/601/seal.png?v={rev}",
        _centred(*SEAL_AT, *SEAL_SIZE), "United States Air Force", "sbox-seal")

    badge = _art(icons, rack["badge"]) if rack.get("badge") else None
    if badge:
        src, bw, bh, _ = badge
        add(f"{src}?v={rev}",
            _centred(*BADGE_AT, bw * BADGE_SCALE, bh * BADGE_SCALE),
            rack.get("badge_name") or "", "sbox-badge")

    patch = _tile(icons, "squadron", squadron_key) if squadron_key else None
    if patch:
        src, pw, ph, _ = patch
        add(f"{src}?v={rev}", _centred(*PATCH_AT, pw, ph), "", "sbox-patch")

    # --- the unit citations ---------------------------------------------
    bars = []
    for c in rack.get("citations") or []:
        art = _art(icons, c["type"])
        if art is not None:
            bars.append((art, c.get("name") or ""))
    if bars:
        widths = [a[1] * CITATION_SCALE for a, _ in bars]
        total = sum(widths) + CITATION_GAP * (len(bars) - 1)
        x = CENTRE_X - total / 2.0
        for (src, w, h, _), name in bars:
            cw, ch = w * CITATION_SCALE, h * CITATION_SCALE
            add(f"{src}?v={rev}", (x, CITATION_Y - ch / 2.0, cw, ch),
                name, "sbox-citation")
            x += cw + CITATION_GAP

    # --- the plate and its rank devices ----------------------------------
    px, py, pw, ph = PLATE
    add(f"/static/images/shadowbox/601/nameplate.png?v={rev}",
        _plate_box(), "", "sbox-plate")

    if rank_id is not None and rank_id in RANK_FILES:
        stem = RANK_FILES[rank_id]
        rw, rh = RANK_SIZE[rank_id]
        cy = py + ph / 2.0
        handed = rank_id not in RANK_UNHANDED
        for side, x in (("left", px - RANK_GAP - rw), ("right", px + pw + RANK_GAP)):
            name = f"{stem}_{side}.png" if handed else f"{stem}.png"
            add(f"/static/images/insignia/{name}?v={rev}",
                (x, cy - rh / 2.0, rw, rh), "", f"sbox-rank sbox-rank-{side}")

    return {
        "rev": REVISION,
        "frame": f"/static/images/shadowbox/601/frame.png?v={rev}",
        "glass": {"src": f"/static/images/shadowbox/601/glass.png?v={rev}",
                  **_pct(GLASS_AT[0], GLASS_AT[1], 1970, 1482)},
        "aspect": round(FRAME[0] / FRAME[1], 6),
        "items": items,
        "plate": _pct(px, py, pw, ph),
    }


def _plate_box() -> tuple:
    """
    Where the brass art goes so that its *plate* lands on ``PLATE``.

    The file is 2508x627 with the plate itself inked from (60, 73) to
    (2451, 530); placing the canvas on the slot would put the brass low and
    to the right of where it was measured.
    """
    ink_x, ink_y, ink_w, ink_h = 60, 73, 2392, 458
    canvas_w, canvas_h = 2508, 627
    scale = PLATE[2] / ink_w
    return (PLATE[0] - ink_x * scale, PLATE[1] - ink_y * scale,
            canvas_w * scale, canvas_h * scale)
