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

The engraving does not follow the reader's language. A shadowbox is an
object hanging on a wall, and its plate is engraved once, in the language
of the air force that issued the awards: English for the Americans,
Russian for the Soviets, Chinese for the Chinese. The reader who wants it
in his own language hovers the plate. The name is never touched.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

from . import medals as medal_art

logger = logging.getLogger(__name__)

# Bumped whenever a constant below moves, so a cached layout is not drawn
# against a frame it was not measured for.
REVISION = 14

# The frame photograph. Every number below is in its pixel space.
FRAME = (2700, 1968)
SOV_FRAME = (2700, 2400)
DPRK_FRAME = (2050, 1860)

# The glass goes on last, over everything. It is stored pre-scaled to the
# size it is placed at, so it only needs an offset; x is not zero because
# the reflection is cropped tighter on the left than the frame is.
GLASS_AT = (0, 0)

# The velvet's horizontal middle, and the one axis everything in the case is
# hung on. Not FRAME[0] / 2: the moulding is a shade wider on the right, and
# rows centred on the true centre of the picture sit visibly off-centre
# inside the box. Every centred piece derives from this rather than carrying
# its own measured x - the reference box was laid out by hand and its badge
# and citation bars ended up 24px right of its seal, patch and plate, which
# is invisible on their own and obvious once they are stacked.
CENTRE_X = 1350
DPRK_CENTRE_X = 1022

# Medals still hang in two rows. The original 14-award rack uses seven in
# each; World War II service adds up to five pieces, so larger racks widen
# progressively to nine or ten rather than opening a third row over the
# emblems and nameplate.
MEDAL_PER_ROW = 7
MEDAL_MAX_PER_ROW = 10
MEDAL_GAP = 14

# Where the top of the ribbon sits for each row. The medals themselves end
# at wildly different heights - the Medal of Honor hangs almost twice as far
# as the Air Medal - so rows are hung from their ribbons, which is how a real
# case is mounted and the only line that reads as straight.
MEDAL_ROW_TOP = (132, 655)

# The lower shelf: the Air Force seal, the aviator badge and the squadron
# patch. Each is centred on its own point rather than sharing a baseline -
# the badge rides higher because the citation bars are pinned beneath it.
SEAL_AT = (CENTRE_X - 675, 1353)
BADGE_AT = (CENTRE_X, 1340)
PATCH_AT = (CENTRE_X + 675, 1365)

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
CITATION_Y = 1520

# The brass plate, given as the ink itself rather than the canvas - the art
# carries a wide transparent margin and placing the canvas would put the
# plate somewhere else entirely.
PLATE = (CENTRE_X - 739 / 2.0, 1647, 739, 142)

# Rank devices butt against the plate at this distance, at their own size,
# centred on the plate. The widest device in the set is the Major General
# star cluster at 394px, which still clears the moulding on both sides.
RANK_GAP = 150

# The Air Force seal is furniture, not an award, and has no atlas tile.
SEAL_SIZE = (295, 294)

# The neck orders are the one set drawn by hand. Their atlas tiles show the
# Medal of Honor on a short drape like any other medal; in a case it hangs
# from its full neck ribbon, which is a different piece of art.
DRAWN_NECK = (601026, 601041)

# A row is scaled down if it will not fit between the mouldings. It only
# bites on a full row of unusually wide tiles, but a medal drawn over the
# frame is worse than one drawn a few per cent small.
INTERIOR = (140, 2560)
DPRK_INTERIOR = (140, 1905)

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

# The Soviet case, measured off docs/reference the same way. It shares the
# Air Force's frame, cloth and brass - the reference box was built on that
# photograph and the moulding matches it to within a pixel - and differs in
# what hangs inside.
#
# Soviet awards divide by how they are worn rather than by precedence alone:
# orders and medals suspended on a pentagonal mount, screw-back orders with
# no ribbon at all, and the Gold Star above them. So the case has a row for
# each instead of the Air Force's single descending line.
# Where every suspended ribbon's ink begins. The reference box had it at
# 150, thirty pixels under the moulding, which read as squeezed; the row and
# the one below it both come down so the case can breathe.
SOV_ROW1_LINE = 195
SOV_STAR_GAP = 125           # the air either side of the Gold Star
SOV_GAP = 48                 # between neighbours, measured ink to ink
SOV_WWII_LINE = 730          # the lower-precedence WWII medal row
SOV_WWII_GAP = 70            # the taller case leaves room to separate them
SOV_ROW2_Y = 1370            # the screw-back orders' middle
# The screw-backs are spaced centre to centre, not packed edge to edge.
# Packing three unequal orders - 290, 269 and 271 wide - centres the row but
# leaves the middle one ten pixels off the axis, which shows against the
# Gold Star and the badge sitting on it.
SOV_ROW2_PITCH = 470
# The middle of this row is on the case's axis, not on where the reference
# box happened to put it: that was laid out by hand and sat three pixels
# left, which shows the moment two pieces are stacked. The arms and the
# squadron sit the same distance out on either side.
SOV_SIDE = 581
SOV_ARMS_AT = (CENTRE_X - SOV_SIDE, 1768)
SOV_BADGE_AT = (CENTRE_X, 1672)
SOV_PROP_AT = (CENTRE_X, 1862)
SOV_PATCH_AT = (CENTRE_X + SOV_SIDE, 1765)
# The plate sits higher than the Air Force's: the shoulder boards are 194
# tall against a rank device's 166, and at the Air Force's height they would
# come within twenty pixels of the moulding.
SOV_PLATE = (CENTRE_X - 738 / 2.0, 2037, 738, 141)
SOV_BOARD_Y = 2110
SOV_BOARD_GAP = 46

# North Korea, measured the same way off its own reference box. The same
# shape as the Soviet case - the hero centred in the top row, the pinned
# orders below, then emblems and the boards - so the two are built from one
# routine and differ only in these numbers.
DPRK_ROW1_LINE = 195
DPRK_ROW1_PITCH = 406
DPRK_ROW2_Y = 770
DPRK_ROW2_PITCH = 412
DPRK_SIDE = 500
DPRK_BADGE_AT = (DPRK_CENTRE_X, 1087)
DPRK_ROUNDEL_AT = (DPRK_CENTRE_X, 1263)
DPRK_ARMS_Y = 1157
DPRK_PATCH_Y = 1161
DPRK_PLATE = (DPRK_CENTRE_X - 738 / 2.0, 1497, 738, 141)
DPRK_BOARD_Y = 1570


class Case(NamedTuple):
    """What differs between one eastern case and the next."""
    folder: str              # its own drawn emblems live here
    row1_line: int           # where the suspended row's ink begins
    row1_pitch: Optional[int]  # centre to centre, or None to pack by ink
    star_gap: int            # the air either side of the hero, when packing
    row2_y: int
    row2_pitch: int
    side: int                # how far out the arms and the squadron sit
    badge_at: Tuple[int, int]
    arms: Tuple[str, Tuple[int, int]]        # file, centre
    extra: Tuple[str, Tuple[int, int]]       # the second drawn emblem
    patch_y: int
    rank_prefix: str
    frame: Tuple[int, int]
    frame_src: str
    glass_src: str
    wwii_line: Optional[int]
    plate: Tuple[float, float, float, float]
    board_y: int
    centre_x: int
    interior: Tuple[int, int]


CASES = {
    501: Case("501", SOV_ROW1_LINE, None, SOV_STAR_GAP, SOV_ROW2_Y, SOV_ROW2_PITCH,
              SOV_SIDE, SOV_BADGE_AT,
              ("USSR_coat_of_arms.png", SOV_ARMS_AT),
              ("VVS_winged_propeller.png", SOV_PROP_AT),
              SOV_PATCH_AT[1], "501", SOV_FRAME,
              "/static/images/shadowbox/501/USSR_Korea_shadowbox.jpg",
              "/static/images/shadowbox/501/USSR_Korea_shadowbox_glass.png",
              SOV_WWII_LINE, SOV_PLATE, SOV_BOARD_Y, CENTRE_X, INTERIOR),
    503: Case("503", DPRK_ROW1_LINE, DPRK_ROW1_PITCH, 0, DPRK_ROW2_Y, DPRK_ROW2_PITCH,
              DPRK_SIDE, DPRK_BADGE_AT,
              ("North_Korea_coat_of_arms.png", (DPRK_CENTRE_X - DPRK_SIDE, DPRK_ARMS_Y)),
              ("North_Korea_roundel.png", DPRK_ROUNDEL_AT),
              DPRK_PATCH_Y, "503", DPRK_FRAME,
              "/static/images/shadowbox/503/North_Korea_shadowbox.jpg",
              "/static/images/shadowbox/503/North_Korea_shadowbox_glass.png",
              None, DPRK_PLATE, DPRK_BOARD_Y, DPRK_CENTRE_X, DPRK_INTERIOR),
}

# Small furniture such as the brass nameplate remains shared even though each
# air force now has its own frame and glass photograph.
FURNITURE = "601"

# Only these two air forces are furnished. The Navy, the Marines and the
# Koreans want their own frame, cloth and devices, and a box built out of
# USAF furniture would be wrong rather than merely plain.
COUNTRIES = (601, 501, 503)


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


_SPANS: Dict[str, Tuple[int, int, int]] = {}


def _span(src: str, data: bytes) -> Tuple[int, int, int]:
    """
    The art's left and right ink edges, and where its ink begins.

    Rows are packed by the edges, not by the canvas: the Soviet tiles carry
    a transparent margin, and spacing three Red Banners by their canvases
    put the outermost one through the moulding.

    The ink top is what the Soviet row hangs from. ``_measure``'s rule -
    the first row reaching most of the band's width - suits a US ribbon,
    which is rectangular and full width at once. A Soviet pentagon ribbon
    widens all the way down, so that rule lands wherever the taper happens
    to cross the threshold: row 44 on a Red Banner against row 34 on the
    Order of Lenin, which set them ten pixels apart on a row that should
    have been level.
    """
    if src not in _SPANS:
        import io
        import numpy as np
        from PIL import Image

        opaque = np.asarray(Image.open(io.BytesIO(data)).convert("RGBA"))[..., 3] > 40
        cols = np.where(opaque.any(axis=0))[0]
        rows = np.where(opaque.any(axis=1))[0]
        _SPANS[src] = ((int(cols.min()), int(cols.max()), int(rows.min()))
                       if len(cols) and len(rows) else (0, 0, 0))
    return _SPANS[src]


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
            _span(f"/api/icon/{kind}/{ident}", data)
        except Exception as exc:                  # pragma: no cover - art only
            logger.warning("Cannot measure %s %s: %s", kind, ident, exc)
            return None
    return (f"/api/icon/{kind}/{ident}",) + _TILES[key]


def _art(icons, award_id: int, renderer=None) -> Optional[Tuple[str, int, int, int]]:
    """
    The source and measurements for one award's full-size art.

    US breast medals use the same loose base and device compositor as the
    full-dress tunic. Soviet-pattern awards, badges and ribbon-only unit
    citations continue to use the game's atlas. The neck orders retain their
    dedicated loose art because they hang from a full neck ribbon.
    """
    composed = (renderer is not None and award_id in medal_art.ribbons.RIBBONS and
                medal_art.ribbons.RIBBONS[award_id].base in medal_art.DRAWN)
    if award_id in _GEOMETRY:
        if award_id in DRAWN_NECK:
            src = f"/static/images/shadowbox/601/{award_id}.png"
        elif composed:
            src = f"/api/medal/{award_id}"
        else:
            src = f"/api/icon/award/{award_id}"
        return (src,) + _GEOMETRY[award_id]
    if award_id in DRAWN_NECK:
        path = (Path(__file__).resolve().parent / "static" / "images" /
                "shadowbox" / "601" / f"{award_id}.png")
        if not path.is_file():
            return None
        data, src = path.read_bytes(), f"/static/images/shadowbox/601/{award_id}.png"
    elif composed:
        data = renderer.png(award_id)
        if data is None:
            return None
        src = f"/api/medal/{award_id}"
    else:
        data = icons.png("award", str(award_id))
        if data is None:
            logger.warning("No atlas tile for award %s", award_id)
            return None
        src = f"/api/icon/award/{award_id}"
    try:
        _GEOMETRY[award_id] = _measure(data)
        _span(src, data)
    except Exception as exc:                      # pragma: no cover - art only
        logger.warning("Cannot measure award %s: %s", award_id, exc)
        return None
    return (src,) + _GEOMETRY[award_id]


def available(country: Optional[int]) -> bool:
    """Whether a box can be built for this pilot's air force."""
    return country in COUNTRIES


def _pct(x: float, y: float, w: float, h: float,
         frame: Tuple[int, int] = FRAME) -> Dict[str, float]:
    """One placement, as percentages of the frame."""
    return {"left": round(100.0 * x / frame[0], 4),
            "top": round(100.0 * y / frame[1], 4),
            "width": round(100.0 * w / frame[0], 4),
            "height": round(100.0 * h / frame[1], 4)}


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
    if not count:
        return []
    per_row = (MEDAL_PER_ROW if count <= 2 * MEDAL_PER_ROW
               else min(MEDAL_MAX_PER_ROW, (count + 1) // 2))
    return medal_art.rows(count, per_row)


def _place_row(art: Sequence[Tuple[int, int, int]], line: float,
               medal_gap: float = MEDAL_GAP, centre_x: int = CENTRE_X,
               interior: Tuple[int, int] = INTERIOR) -> List[tuple]:
    """
    Lay a row of medals out around ``CENTRE_X``, hung from a common ribbon.

    Every tile is a different size and carries a different amount of clear
    space above its ribbon, so neither a fixed pitch nor a shared top edge
    will do. Each piece is placed by its own ribbon top, which puts all the
    ribbons on ``line`` - the way a case is actually mounted, and the only
    line in a row of medals that reads as straight.
    """
    widths = [w for w, _, _ in art]
    total = sum(widths) + medal_gap * (len(widths) - 1)
    room = interior[1] - interior[0]
    scale = min(1.0, room / total) if total else 1.0
    gap = medal_gap * scale
    x = centre_x - total * scale / 2.0
    out = []
    for w, h, ribbon in art:
        out.append((x, line - ribbon * scale, w * scale, h * scale))
        x += w * scale + gap
    return out


def _centred_ink(src: str, cx: float, cy: float, w: float, h: float) -> tuple:
    """
    Centre a piece on its own ink rather than on its canvas.

    The pilot's badge is 465 wide with its ink from 2 to 454, so its middle
    is four pixels left of the canvas middle; centring the canvas hangs it
    visibly off the line it shares with the propeller beneath it.
    """
    il, ir, _ = _SPANS.get(src, (0, int(w) - 1, 0))
    return (cx - (il + ir) / 2.0, cy - h / 2.0, w, h)


def _centred(cx: float, cy: float, w: float, h: float) -> tuple:
    return (cx - w / 2.0, cy - h / 2.0, w, h)


# How a rank is engraved on brass. An engraver shortens the rank and leaves
# the man's name alone - "2nd Lt. Meade Bennett", never "Second Lieutenant
# M. Be...". Spelling the rank out was costing the name its letters.
#
# These are abbreviations, not translations. The plate carries the issuing
# air force's own language and never the reader's, so there is one form per
# rank per country and no locale file is involved. Only the long compound
# ranks are shortened; Captain, Major and Colonel are already short enough
# to engrave, and shortening them would look affected rather than correct.
#
# 502 and 503 are absent on purpose. The Chinese ranks are two characters
# each and the Korean ones are romanised single words - Sojwa, Taejwa -
# so there is nothing to shorten and a wrong guess would be worse than none.
RANK_ABBR = {
    601: {0: "2nd Lt.", 1: "1st Lt.", 2: "Captain", 3: "Major",
          4: "Lt. Col.", 5: "Colonel", 6: "Brig. Gen.", 7: "Maj. Gen."},
    # The Navy ladder is its own: a lieutenant junior grade is never "1st Lt."
    602: {0: "Ensign", 1: "Lt. (j.g.)", 2: "Lieutenant", 3: "Lt. Cdr.",
          4: "Commander", 5: "Captain", 6: "Rear Adm. (l.h.)",
          7: "Rear Adm."},
    # The Marines wear the Army ladder, as the game's own names show.
    603: {0: "2nd Lt.", 1: "1st Lt.", 2: "Captain", 3: "Major",
          4: "Lt. Col.", 5: "Colonel", 6: "Brig. Gen.", 7: "Maj. Gen."},
    # Soviet practice shortens the compounds the same way: ст. лейтенант,
    # ген.-майор. Подполковник is one word and is written out.
    501: {1: "Ст. лейтенант", 6: "Ген.-майор", 7: "Ген.-лейтенант"},
}


def engraved_rank(country: Optional[int], rank_id: Optional[int],
                  full: str) -> str:
    """The rank as it goes on the brass, falling back to the full name."""
    if country is None or rank_id is None:
        return full
    return RANK_ABBR.get(country, {}).get(rank_id) or full


def plate_text(rank: str, name: str, country: Optional[int] = None,
               rank_id: Optional[int] = None) -> Dict[str, str]:
    """
    The engraving, in full and abbreviated.

    Both go to the page because only the page knows how wide the text
    actually runs in the font it loaded. It measures the full form, and
    falls back to the initial when the plate cannot hold it.

    The rank is shortened first and the name kept whole, so the initial is
    now a last resort for a genuinely long name rather than the routine
    outcome of a long rank.
    """
    short_rank = engraved_rank(country, rank_id, rank)
    full = f"{short_rank} {name}".strip()
    parts = name.split()
    short = (f"{short_rank} {parts[0][0]}. {' '.join(parts[1:])}".strip()
             if len(parts) > 1 and parts[0] else full)
    return {"full": full, "short": short, "rank_engraved": short_rank}


def layout(rack: Dict[str, Any], rank_id: Optional[int], squadron_key: Optional[str],
           icons, country: int = 601, rev: str = "", medal_renderer=None) -> Dict[str, Any]:
    """
    Every piece in the box, in the order it should be drawn.

    ``rack`` is the tunic payload the detail page already builds - the same
    medals, citations and badge the pilot wears - so the box and the uniform
    can never disagree about what he has been given. ``icons`` is the sheet
    reader the medals and badges are sliced from.
    """
    case = CASES.get(country)
    items, plate = (_eastern(rack, rank_id, squadron_key, icons, rev, case,
                              medal_renderer)
                    if case else _usaf(rack, rank_id, squadron_key, icons, rev,
                                       medal_renderer))
    frame = case.frame if case else FRAME
    frame_src = (case.frame_src if case else
                 f"/static/images/shadowbox/{FURNITURE}/USAF_Korea_shadowbox_frame.jpg")
    glass_src = (case.glass_src if case else
                 f"/static/images/shadowbox/{FURNITURE}/glass.png")
    return {
        "rev": REVISION,
        "frame": f"{frame_src}?v={rev}",
        "glass": {"src": f"{glass_src}?v={rev}",
                  **_pct(GLASS_AT[0], GLASS_AT[1], *frame, frame=frame)},
        "aspect": round(frame[0] / frame[1], 6),
        # The frame's own pixel size. The page lays the case out in
        # percentages and does not need it, but an exported picture should
        # be cut at the size the artwork was drawn at, not at whatever the
        # window happened to be.
        "size": list(frame),
        "items": items,
        "plate": _pct(*plate, frame=frame),
    }


def _eastern(rack, rank_id, squadron_key, icons, rev, case: "Case",
             medal_renderer=None):
    """
    A Soviet-pattern case: suspended awards, then the orders worn without a
    ribbon, then the arms, the pilot's badge and his squadron, over the
    boards and the plate.

    The Soviet and North Korean boxes are the same arrangement with
    different numbers, so ``case`` carries what differs.
    """
    SOV_ROW1_LINE, SOV_ROW2_Y = case.row1_line, case.row2_y
    SOV_ROW2_PITCH, SOV_STAR_GAP = case.row2_pitch, case.star_gap
    SOV_BADGE_AT = case.badge_at
    centre_x = case.centre_x
    SOV_PATCH_AT = (centre_x + case.side, case.patch_y)
    items: List[Dict[str, Any]] = []

    def add(src, box, name="", cls=""):
        x, y, w, h = box
        items.append({"src": src, "name": name, "cls": cls,
                      **_pct(x, y, w, h, frame=case.frame)})

    def art_of(award_id, name=""):
        got = _art(icons, award_id, medal_renderer)
        return None if got is None else (got, name)

    # --- row one: what hangs from a ribbon ------------------------------
    # The Gold Star takes the middle with air either side. A repeat awarding
    # is a separate order rather than a device, so the Red Banners are three
    # of the same picture; they stay together on the left, highest awarding
    # first, and the rest follow the star in precedence. With no repeat to
    # group, the row simply splits around the star.
    bar = [m["type"] for m in rack.get("medals") or []]
    names = {m["type"]: m.get("name") or "" for m in rack.get("medals") or []}
    wwii = ([award_id for award_id in bar if award_id in medal_art.SOVIET_WWII]
            if case.wwii_line is not None else [])
    if wwii:
        bar = [award_id for award_id in bar if award_id not in medal_art.SOVIET_WWII]
    repeats = _repeat_group(bar)
    if repeats:
        # placed outward from the star, so the first awarding ends up
        # nearest it and the third furthest out, as the reference box has it
        left = list(repeats)
        right = [a for a in bar if a not in repeats]
    else:
        half = len(bar) // 2
        left, right = bar[:half], bar[half:]

    hero = (rack.get("hero") or {}).get("type") if isinstance(rack.get("hero"), dict) else None
    star = art_of(hero, (rack.get("hero") or {}).get("name", "")) if hero else None
    if star:
        (src, w, h, ribbon), nm = star
        sl, sr, st = _SPANS.get(src, (0, w - 1, 0))
        add(f"{src}?v={rev}",
            (centre_x - (sl + sr) / 2.0, SOV_ROW1_LINE - st, w, h),
            nm, "sbox-medal")
        # Either a fixed centre-to-centre pitch, or packed outward from the
        # hero by the art's own edges where the case gives no pitch.
        step = case.row1_pitch
        x = (centre_x - step if step
             else centre_x - (sr - sl + 1) / 2.0 - SOV_STAR_GAP)
        for a in left:
            got = art_of(a, names.get(a, ""))
            if not got:
                continue
            (s, aw, ah, rb), nm = got
            il, ir, it = _SPANS.get(s, (0, aw - 1, 0))
            place = x - (il + ir) / 2.0 if step else x - ir - 1
            add(f"{s}?v={rev}", (place, SOV_ROW1_LINE - it, aw, ah), nm, "sbox-medal")
            x -= step if step else (ir - il + 1) + SOV_GAP
        x = (centre_x + step if step
             else centre_x + (sr - sl + 1) / 2.0 + SOV_STAR_GAP)
        for a in right:
            got = art_of(a, names.get(a, ""))
            if not got:
                continue
            (s, aw, ah, rb), nm = got
            il, ir, it = _SPANS.get(s, (0, aw - 1, 0))
            place = x - (il + ir) / 2.0 if step else x - il
            add(f"{s}?v={rev}", (place, SOV_ROW1_LINE - it, aw, ah), nm, "sbox-medal")
            x += step if step else (ir - il + 1) + SOV_GAP
    else:
        row = [art_of(a, names.get(a, "")) for a in bar]
        row = [r for r in row if r]
        boxes = _place_row([(w, h, rb) for (_, w, h, rb), _ in row],
                           SOV_ROW1_LINE, centre_x=centre_x,
                           interior=case.interior)
        for ((s, *_), nm), box in zip(row, boxes):
            add(f"{s}?v={rev}", box, nm, "sbox-medal")

    # The lower-precedence WWII campaign and victory medals form their own
    # centred row in the taller Soviet case.  This preserves the established
    # Hero/order arrangement above and keeps every pentagonal mount at the
    # same physical size.
    if wwii:
        row = [art_of(a, names.get(a, "")) for a in wwii]
        row = [r for r in row if r]
        boxes = _place_row([(w, h, rb) for (_, w, h, rb), _ in row],
                           case.wwii_line, SOV_WWII_GAP, centre_x,
                           case.interior)
        for ((s, *_), nm), box in zip(row, boxes):
            add(f"{s}?v={rev}", box, nm, "sbox-medal sbox-wwii-medal")

    # --- row two: the screw-backs, in precedence -------------------------
    pinned = [art_of(m["type"], m.get("name") or "") for m in rack.get("pinned") or []]
    pinned = [p for p in pinned if p]
    if pinned:
        first = centre_x - SOV_ROW2_PITCH * (len(pinned) - 1) / 2.0
        for i, ((s, w, h, _), nm) in enumerate(pinned):
            add(f"{s}?v={rev}",
                _centred_ink(s, first + i * SOV_ROW2_PITCH, SOV_ROW2_Y, w, h),
                nm, "sbox-pinned")

    # --- row three: arms, badge and squadron -----------------------------
    for name, at in (case.arms, case.extra):
        art = (Path(__file__).resolve().parent / "static" / "images" /
               "shadowbox" / case.folder / name)
        if not art.is_file():
            logger.warning("Case emblem missing: %s", art.name)
            continue
        src = f"/static/images/shadowbox/{case.folder}/{name}"
        if src not in _SPANS:
            _span(src, art.read_bytes())
        w, h = _measure(art.read_bytes())[:2]
        add(f"{src}?v={rev}", _centred_ink(src, *at, w, h), "", "sbox-emblem")

    wings = rack.get("wings")
    badge = art_of(wings["type"], wings.get("name") or "") if wings else None
    if badge:
        (s, w, h, _), nm = badge
        add(f"{s}?v={rev}", _centred_ink(s, *SOV_BADGE_AT, w, h), nm, "sbox-badge")

    # A squadron belongs to one air force, so a key from another is not
    # drawn at all rather than put a foreign patch in the case. Real careers
    # always agree; the preview switch is what can disagree.
    patch = (_tile(icons, "squadron", squadron_key)
             if squadron_key and str(squadron_key).startswith(case.folder) else None)
    if patch:
        s, w, h, _ = patch
        add(f"{s}?v={rev}", _centred_ink(s, *SOV_PATCH_AT, w, h), "", "sbox-patch")

    # --- the plate and the shoulder boards -------------------------------
    px, py, pw, ph = case.plate
    add(f"/static/images/shadowbox/{FURNITURE}/nameplate.png?v={rev}",
        _plate_box(case.plate), "", "sbox-plate")

    board = (_tile(icons, "rank", f"{case.rank_prefix}{rank_id}")
             if rank_id is not None else None)
    if board:
        s, w, h, _ = board
        il, ir, _ = _SPANS.get(s, (0, w - 1, 0))
        ink = ir - il + 1
        # A general's board is 504 wide against 461 for every other rank, and
        # at the standard gap it would run through the moulding. The gap
        # closes instead, the same amount on both sides, so the pair stays
        # symmetrical and inside the cloth whatever the rank.
        room = min(px - case.interior[0], case.interior[1] - (px + pw))
        gap = max(0.0, min(float(SOV_BOARD_GAP), room - ink))
        y = case.board_y - h / 2.0
        add(f"{s}?v={rev}", (px - gap - ink - il, y, w, h), "",
            "sbox-board sbox-board-left")
        # The right board is this tile mirrored in the stylesheet, so its ink
        # ends up (w - 1 - ir) in from the element's left edge.
        add(f"{s}?v={rev}", (px + pw + gap - (w - 1 - ir), y, w, h), "",
            "sbox-board sbox-board-right")

    return items, case.plate


def _repeat_group(bar: Sequence[int]) -> List[int]:
    """
    The awards in ``bar`` that are repeat awardings of one order.

    Three Red Banners are three tiles of the same base; nothing else in a
    Soviet rack repeats, so the longest such run is the group to keep whole.
    """
    from . import ribbons

    runs: Dict[int, List[int]] = {}
    for aid in bar:
        spec = ribbons.RIBBONS.get(aid)
        if spec is not None:
            runs.setdefault(spec.base, []).append(aid)
    best = max(runs.values(), key=len, default=[])
    return best if len(best) > 1 else []


def _usaf(rack: Dict[str, Any], rank_id: Optional[int], squadron_key: Optional[str],
          icons, rev: str, medal_renderer=None):
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
        art = _art(icons, award_id, medal_renderer)
        if art is None:
            continue
        src, w, h, ribbon = art
        worn.append({"name": name, "src": f"{src}?v={rev}", "art": (w, h, ribbon)})

    # The case has two rows. A malformed preview can still ask for more than
    # twenty pieces; anything beyond the second row is dropped rather than
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
    add(f"/static/images/shadowbox/{FURNITURE}/nameplate.png?v={rev}",
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

    return items, PLATE


def _plate_box(slot=None) -> tuple:
    """
    Where the brass art goes so that its *plate* lands on ``slot``.

    The file is 2508x627 with the plate itself inked from (60, 73) to
    (2451, 530); placing the canvas on the slot would put the brass low and
    to the right of where it was measured.
    """
    slot = PLATE if slot is None else slot
    ink_x, ink_y, ink_w = 60, 73, 2392
    canvas_w, canvas_h = 2508, 627
    scale = slot[2] / ink_w
    return (slot[0] - ink_x * scale, slot[1] - ink_y * scale,
            canvas_w * scale, canvas_h * scale)
