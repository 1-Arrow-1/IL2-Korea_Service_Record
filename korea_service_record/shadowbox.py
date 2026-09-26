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

from typing import Any, Dict, List, Optional, Sequence

from . import medals as medal_art
from . import ribbons

# Bumped whenever a constant below moves, so a cached layout is not drawn
# against a frame it was not measured for.
REVISION = 1

# The frame photograph. Every number below is in its pixel space.
FRAME = (2050, 1860)

# The glass goes on last, over everything. It is stored pre-scaled to the
# size it is placed at, so it only needs an offset; x is not zero because
# the reflection is cropped tighter on the left than the frame is.
GLASS_AT = (53, 0)

# The velvet's horizontal middle. Not FRAME[0] / 2: the moulding is a shade
# wider on the right, and rows centred on the true centre of the picture sit
# visibly off-centre inside the box.
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
BADGE_AT = (1046, 1226)
PATCH_AT = (1602, 1325)

# The aviator badge is mounted slightly over its atlas size. It is a small
# piece of art beside two 290px discs and reads as an afterthought at 1:1.
BADGE_SCALE = 1.05

# The squadron emblem is a 320px tile in the game's atlas, mounted a little
# under size so it does not outweigh the seal facing it.
PATCH_WIDTH = 285

# Unit citations, pinned in a line beneath the badge. The width is measured;
# the height follows the ribbon's own aspect rather than the reference box,
# which stretched them.
CITATION_WIDTH = 228
CITATION_GAP = 64
CITATION_Y = 1427

# The brass plate, given as the ink itself rather than the canvas - the art
# carries a wide transparent margin and placing the canvas would put the
# plate somewhere else entirely.
PLATE = (656, 1547, 739, 142)

# Rank devices butt against the plate at this distance, at their own size,
# centred on the plate. The widest device in the set is the Major General
# star cluster at 394px, which still clears the moulding on both sides.
RANK_GAP = 68

# Art whose size cannot be asked of the atlas.
SEAL_SIZE = (295, 294)
NECK_SIZE = (348, 496)
MEDAL_SIZE = medal_art.DRAPE               # (224, 474)
BADGE_SIZE = {601001: (448, 133), 601027: (456, 208), 601040: (456, 208)}

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


def available(country: Optional[int]) -> bool:
    """Whether a box can be built for this pilot's air force."""
    return country in COUNTRIES


def _pct(x: float, y: float, w: float, h: float) -> Dict[str, float]:
    """One placement, as percentages of the frame."""
    return {"left": round(100.0 * x / FRAME[0], 4),
            "top": round(100.0 * y / FRAME[1], 4),
            "width": round(100.0 * w / FRAME[0], 4),
            "height": round(100.0 * h / FRAME[1], 4)}


def _row_sizes(count: int) -> List[int]:
    """
    How many medals hang in each row, top to bottom.

    ``medals.rows`` puts the short row on top, which is how a rack is worn
    and how the reference box is arranged.
    """
    return medal_art.rows(count, MEDAL_PER_ROW) if count else []


def _place_row(widths: Sequence[int], top: int, heights: Sequence[int]) -> List[tuple]:
    """
    Lay a row of art out around ``CENTRE_X``, hung from a common top edge.

    Widths vary - the Medal of Honor's neck ribbon is half again as wide as
    a drape - so the row is measured before it is placed rather than being
    dropped onto a fixed pitch.
    """
    total = sum(widths) + MEDAL_GAP * (len(widths) - 1)
    x = CENTRE_X - total / 2.0
    out = []
    for w, h in zip(widths, heights):
        out.append((x, top, w, h))
        x += w + MEDAL_GAP
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
           rev: int = 0) -> Dict[str, Any]:
    """
    Every piece in the box, in the order it should be drawn.

    ``rack`` is the tunic payload the detail page already builds - the same
    medals, citations and badge the pilot wears - so the box and the uniform
    can never disagree about what he has been given.
    """
    items: List[Dict[str, Any]] = []

    def add(src: str, box: tuple, name: str = "", cls: str = "") -> None:
        x, y, w, h = box
        items.append({"src": src, "name": name, "cls": cls, **_pct(x, y, w, h)})

    svc = f"&svc={rack['svc']}" if rack.get("svc") else ""
    mrev = rack.get("medal_rev", 0)

    # --- the medals ----------------------------------------------------
    # The neck order is worn at the throat and leads the line; the rest
    # follow in precedence, which is the order the rack already holds them.
    worn: List[Dict[str, Any]] = []
    neck = rack.get("neck")
    if neck:
        worn.append({"type": neck, "name": rack.get("neck_name") or "",
                     "size": NECK_SIZE,
                     "src": f"/static/images/shadowbox/601/{neck}.png?v={rev}"})
    for piece in rack.get("medals") or []:
        worn.append({"type": piece["type"], "name": piece.get("name") or "",
                     "size": MEDAL_SIZE,
                     "src": f"/api/medal/{piece['type']}?v={mrev}{svc}"})

    placed = 0
    for row_index, count in enumerate(_row_sizes(len(worn))):
        row = worn[placed:placed + count]
        placed += count
        # A pilot cannot hold more than two rows' worth, but a preview rack
        # can ask for anything; anything past the second row is dropped
        # rather than drawn over the seal.
        if row_index >= len(MEDAL_ROW_TOP):
            break
        boxes = _place_row([m["size"][0] for m in row],
                           MEDAL_ROW_TOP[row_index],
                           [m["size"][1] for m in row])
        for medal, box in zip(row, boxes):
            add(medal["src"], box, medal["name"], "sbox-medal")

    # --- the lower shelf ------------------------------------------------
    add(f"/static/images/shadowbox/601/seal.png?v={rev}",
        _centred(*SEAL_AT, *SEAL_SIZE), "United States Air Force", "sbox-seal")

    badge = rack.get("badge")
    if badge:
        bw, bh = BADGE_SIZE.get(badge, (456, 208))
        add(f"/api/icon/award/{badge}?v={rev}",
            _centred(*BADGE_AT, bw * BADGE_SCALE, bh * BADGE_SCALE),
            rack.get("badge_name") or "", "sbox-badge")

    if squadron_key:
        add(f"/api/icon/squadron/{squadron_key}?v={rev}",
            _centred(*PATCH_AT, PATCH_WIDTH, PATCH_WIDTH), "", "sbox-patch")

    # --- the unit citations ---------------------------------------------
    cites = rack.get("citations") or []
    if cites:
        ch = CITATION_WIDTH * ribbons.CANVAS[1] / ribbons.CANVAS[0]
        total = len(cites) * CITATION_WIDTH + CITATION_GAP * (len(cites) - 1)
        x = CENTRE_X - total / 2.0
        for c in cites:
            add(f"/api/ribbon/{c['type']}?v={rack.get('rev', 0)}{svc}",
                (x, CITATION_Y - ch / 2.0, CITATION_WIDTH, ch),
                c.get("name") or "", "sbox-citation")
            x += CITATION_WIDTH + CITATION_GAP

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
