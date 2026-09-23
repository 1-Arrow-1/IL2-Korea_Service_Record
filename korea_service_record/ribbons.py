"""
Ribbon rack: the service ribbons a pilot wears on the tunic, composed from
the mod's own art rather than the game's medal atlases.

    static/images/ribbons/<base award>.png     bar, no devices (440x120 US, 420x140 Soviet pattern)
    static/images/ribbons/olc_bronze.png ...   devices, any size (scaled down to the bar)
    static/images/ribbons/frame_gold.png       480x160, the unit-citation frame

Every award id the USAF and Navy ladders can hand out maps to one base ribbon
and the devices worn on it: oak leaf clusters for the Air Force, gold/silver
award stars for the Navy, the bronze V of a Bronze Star awarded for valour,
and the smaller service stars of the Korean Service Medal. Twin ids that the
awards.cfg needs for one rung map to the same composition, so the rack never
shows a rung twice.

Order of wear is the Army's of 1950-53, which the Air Force followed until
its own manual: decorations by precedence, the Purple Heart *after* the
Commendation as it was then (it moved up only in 1985), the unit citations
next as the Air Force wore them on the left with everything else, then the
service medals, the foreign unit award, and the UN medal last.

A composed ribbon is 480x160: the bar centred with a 20 px margin all round,
so the gold frame of a unit citation overhangs without changing the grid.
"""

from __future__ import annotations

import io
import logging
import math
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

logger = logging.getLogger(__name__)

ART = Path(__file__).resolve().parent / "static" / "images" / "ribbons"
# Bump whenever the composition or the art changes: it goes into the image
# URLs, so browsers that were told to cache a ribbon for a year re-fetch it.
REVISION = 20
# US bars are 1 3/8 x 3/8 inch (11:3); Soviet-pattern bars (USSR, DPRK) are
# 24 x 8 mm (3:1). Each sits centred on a canvas 20 px bigger all round, so a
# unit citation's frame can overhang without changing the grid.
MARGIN = 20
GEOMETRY = {"us": (440, 120), "sov": (420, 140)}
BAR = GEOMETRY["us"]
CANVAS = (BAR[0] + 2 * MARGIN, BAR[1] + 2 * MARGIN)

# docs/DEVICE_RULES.md governs everything below. Devices sit 0.02 W apart;
# a full row that would not fit at that gap closes up to 0.015 W, and is
# never shrunk - if it still overhangs, the art is oversized (four 5/16"
# Navy stars come to 1.00 W at the tight gap, as on a real bar).
DEVICE_GAP = round(0.02 * BAR[0])
DEVICE_GAP_TIGHT = round(0.015 * BAR[0])
# Regulation device sizes on a 1 3/8 x 3/8 inch bar, as a fraction of the bar:
# an oak leaf cluster is 5/16 inch wide, the V 1/4 inch tall, a service star
# 3/16 inch, a Navy repeat-award star 5/16 inch. Every device is drawn at
# the same scale on every ribbon - a four-cluster bar must not carry smaller
# clusters than a three-cluster one.
OVERSCALE = 1.0
DEVICE_SIZE = {"olc": ("w", OVERSCALE * 5 / 16 / (11 / 8)), "v": ("h", OVERSCALE * 1 / 4 / (3 / 8)),
               "star": ("h", OVERSCALE * 3 / 16 / (3 / 8)),
               "award_star": ("h", OVERSCALE * 5 / 16 / (3 / 8))}


# Stars worn point-down, the Korean War naval practice (DEVICE_RULES.md
# 4, 5, 9). The campaign stars of a medal both services wear - the Korean
# Service Medal above all - are the same award but a different device
# depending on who wears it, so they get their own names and NAVAL_STAR
# swaps them in when the wearer is a sailor or a Marine. A naval silver
# star is 5/16 in, where the Army's is 3/16.
NAVY_STARS = ("star_gold", "star_silver_large", "star_bronze_navy", "star_silver_navy")
# 5/16 in: the repeat-award stars of a personal decoration. A campaign star
# is 3/16 whatever its metal and whoever wears it - the silver one stands
# for five bronze and is drawn to the same size beside them (the owner's
# correction 2026-09-22 to DEVICE_RULES.md 5, which had the naval silver
# campaign star larger).
BIG_STARS = ("star_gold", "star_silver_large")
NAVAL_STAR = {"star_bronze": "star_bronze_navy", "star_silver": "star_silver_navy"}
SILVER_STARS = ("star_silver", "star_silver_large", "star_silver_navy")


def row_origin(names: List[str], widths: List[int], gap: int, room: int) -> int:
    """
    Where a row of devices starts, in a ribbon `room` wide: centred as a
    group, unless a silver star with other stars round it is in the row -
    then the silver star itself sits on the centre line and the others
    hang off it (DEVICE_RULES.md 5, 6, 7), so a silver-and-one-bronze KSM
    reads bronze left of centre, silver on it.
    """
    width = sum(widths) + gap * (len(widths) - 1)
    anchor = next((i for i, n in enumerate(names) if n in SILVER_STARS), None)
    if anchor is None or len(names) < 2 or not any(n.startswith("star") for i, n in enumerate(names) if i != anchor):
        return (room - width) // 2
    before = sum(widths[:anchor]) + gap * anchor
    return room // 2 - before - widths[anchor] // 2


def _around(centre: List[str], others: List[str]) -> List[str]:
    """`others` arranged round `centre`: the first to the viewer's left,
    the second to the right, and so on outward. No centre: just the row."""
    if not centre:
        return others
    left = (len(others) + 1) // 2
    return others[:left] + centre + others[left:]


def fit_row(widths: List[int], room: int, gap: int, tight: int) -> Tuple[int, int]:
    """
    The gap and total width of a row of devices: the standard gap, closed
    up towards the tight one only when the row would not fit, never a
    shrunken device (DEVICE_RULES.md 7, 10). Returns (gap, width); a width
    beyond the room means the art is oversized, and is logged, not hidden.
    """
    n = len(widths)
    total = sum(widths)
    if n > 1 and total + gap * (n - 1) > room:
        gap = max(tight, (room - total) // (n - 1))
    width = total + gap * (n - 1)
    if width > room:
        logger.warning("Device row %d px wide for a %d px ribbon: art oversized", width, room)
    return gap, width


def geometry(award_id: int) -> str:
    """Which bar pattern an award's country wears."""
    return "sov" if str(award_id).startswith(("501", "503")) else "us"


class Ribbon(NamedTuple):
    base: int                 # award id whose bar is the artwork
    olc_bronze: int = 0
    olc_silver: int = 0
    valour: bool = False      # the bronze V
    star_bronze: int = 0
    star_silver: int = 0
    star_gold: int = 0        # Navy 5/16-inch repeat-award star
    star_silver_large: int = 0
    framed: bool = False      # unit citation
    repeat: int = 1           # Soviet repeat awardings: one more identical bar each

    @property
    def devices(self) -> List[str]:
        """
        Device files left to right as worn: the V first, then clusters
        (silver before bronze), then stars. Stars of either kind keep a
        silver one in the middle with the bronze or gold ones around it,
        the first to the viewer's left (DEVICE_RULES.md 5, 6; the KSM's
        silver-and-one-bronze reads bronze, silver).
        """
        # Navy stars are separate device names so the renderer can turn them
        # point-down (Korean War Navy/USMC practice - DEVICE_RULES.md 4, 5, 9).
        out: List[str] = []
        award_stars = _around(["star_silver_large"] * self.star_silver_large,
                              ["star_gold"] * self.star_gold)
        if self.valour and award_stars:
            # On the naval Bronze Star the first repeat star is to the
            # wearer's right of the V and the second is placed opposite it.
            out.append(award_stars.pop(0))
            out.append("v_device")
            out += award_stars
        elif self.valour:
            out.append("v_device")
        out += ["olc_silver"] * self.olc_silver + ["olc_bronze"] * self.olc_bronze
        out += _around(["star_silver"] * self.star_silver, ["star_bronze"] * self.star_bronze)
        if not self.valour:
            out += award_stars
        return out


def _ladder(base: int, ids: List[int], silver_at: Optional[int] = None,
            **extra) -> Dict[int, Ribbon]:
    """ids[n] is the (n+1)th award: n bronze clusters, or one silver at the end."""
    out = {}
    for n, aid in enumerate(ids):
        if silver_at is not None and aid == silver_at:
            out[aid] = Ribbon(base, olc_silver=1, **extra)
        else:
            out[aid] = Ribbon(base, olc_bronze=n, **extra)
    return out


def _navy_ladder(base: int, ids: List[int], silver_at: Optional[int] = None,
                 **extra) -> Dict[int, Ribbon]:
    """Navy repeats: 5/16-inch gold stars, one silver star for five gold."""
    out = {}
    for n, aid in enumerate(ids):
        if silver_at is not None and aid == silver_at:
            out[aid] = Ribbon(base, star_silver_large=1, **extra)
        else:
            out[aid] = Ribbon(base, star_gold=n, **extra)
    return out


# Award id -> what is worn. Listed in order of precedence, highest first;
# PRECEDENCE below is derived from this order, so keep it that way.
RIBBONS: Dict[int, Ribbon] = {}
RIBBONS.update(_ladder(601026, [601026, 601041]))                                   # Medal of Honor
RIBBONS.update(_ladder(601021, [601021, 601022, 601023, 601024, 601025]))           # DSC
RIBBONS.update(_ladder(601052, [601052]))                                           # DSM
RIBBONS.update(_ladder(601018, [601018, 601019, 601020, 601050, 601051]))           # Silver Star
RIBBONS.update(_ladder(601017, [601017]))                                           # Legion of Merit
RIBBONS.update(_ladder(601011, [601011, 601012, 601013, 601014, 601015, 601016],
                       silver_at=601016))                                           # DFC
RIBBONS.update({                                                                    # Bronze Star, valour
    601058: Ribbon(601008, valour=True),
    601059: Ribbon(601008, valour=True, olc_bronze=1),
    601061: Ribbon(601008, valour=True, olc_bronze=1),
    601060: Ribbon(601008, valour=True, olc_bronze=2),
    601062: Ribbon(601008, valour=True, olc_bronze=2),
})
RIBBONS.update(_ladder(601008, [601008, 601009, 601010]))                           # Bronze Star, merit
RIBBONS.update(_ladder(601002, [601002, 601003, 601004, 601005, 601006, 601007],
                       silver_at=601007))                                           # Air Medal
RIBBONS.update(_ladder(601054, [601054, 601055, 601056, 601057]))                   # Commendation
RIBBONS.update(_ladder(601028, [601028, 601029, 601030]))                           # Purple Heart

# Navy / Marine Corps personal and unit awards. Shared medals use the same
# base art as their USAF counterparts but carry naval 5/16-inch award stars.
RIBBONS.update(_navy_ladder(601026, [602027, 602038]))                              # Medal of Honor
RIBBONS.update(_navy_ladder(602021, [602021, 602022, 602023, 602024, 602025, 602026],
                            silver_at=602026))                                      # Navy Cross
RIBBONS[602031] = Ribbon(602031)                                                    # Navy DSM
RIBBONS.update(_navy_ladder(601018, [602018, 602019, 602020, 602042, 602043]))      # Silver Star
RIBBONS[602017] = Ribbon(601017)                                                    # Legion of Merit
RIBBONS.update(_navy_ladder(601011, [602011, 602012, 602013, 602014, 602015, 602016],
                            silver_at=602016))                                      # DFC
RIBBONS.update({                                                                    # Bronze Star with V
    602048: Ribbon(601008, valour=True),
    602049: Ribbon(601008, valour=True, star_gold=1),
    602051: Ribbon(601008, valour=True, star_gold=1),
    602050: Ribbon(601008, valour=True, star_gold=2),
    602052: Ribbon(601008, valour=True, star_gold=2),
})
RIBBONS.update(_navy_ladder(601008, [602008, 602009, 602010]))                      # Bronze Star, merit
RIBBONS.update(_navy_ladder(601002, [602002, 602003, 602004, 602005, 602006, 602007],
                            silver_at=602007))                                      # Air Medal
RIBBONS.update(_navy_ladder(602032, [602032, 602035, 602036, 602037]))              # Commendation
RIBBONS.update(_navy_ladder(601028, [602028, 602029, 602030]))                      # Purple Heart
RIBBONS.update(_navy_ladder(602033, [602033, 602039, 602040, 602041]))              # Navy PUC
RIBBONS.update(_navy_ladder(602034, [602034, 602044, 602045, 602046, 602047]))      # Navy Unit Commendation

RIBBONS.update(_ladder(601042, [601042, 601044, 601045, 601046], framed=True))      # DUC
RIBBONS.update(_ladder(601053, [601053]))                                           # NDSM
RIBBONS.update({                                                                    # Korean Service Medal
    601031: Ribbon(601031),
    601032: Ribbon(601031, star_bronze=1),
    601033: Ribbon(601031, star_bronze=2),
    601034: Ribbon(601031, star_bronze=3),
    601035: Ribbon(601031, star_bronze=4),
    601036: Ribbon(601031, star_silver=1),
    601037: Ribbon(601031, star_silver=1, star_bronze=1),
    601038: Ribbon(601031, star_silver=1, star_bronze=2),
})
# Repeat ROK citations remain separate awards in the record, but authorize
# no repeat devices: every rung wears the same single, plain framed ribbon.
RIBBONS.update({aid: Ribbon(601043, framed=True)
                for aid in (601043, 601047, 601048, 601049)})                    # ROK PUC
RIBBONS.update(_ladder(601039, [601039]))                                           # UN Korean Service Medal

# USSR, in order of seniority of the orders (Lenin, Red Banner, Suvorov,
# Nevsky, Red Star) and then the medals, with the Gold Star of a Hero first
# as it is worn above everything. A second or third awarding of the Red
# Banner is a second or third order, worn as another identical bar.
RIBBONS.update({
    501022: Ribbon(501022),                       # Hero of the Soviet Union
    501024: Ribbon(501024),                       # Order of Lenin
    501020: Ribbon(501016, repeat=3),             # Red Banner, 3rd awarding
    501018: Ribbon(501016, repeat=2),             # Red Banner, 2nd awarding
    501016: Ribbon(501016),                       # Red Banner
    501014: Ribbon(501014),                       # Suvorov 3rd Class
    501012: Ribbon(501012),                       # Alexander Nevsky
    501006: Ribbon(501006),                       # Red Star
    501002: Ribbon(501002),                       # Medal for Courage
    501004: Ribbon(501004),                       # Medal for Battle Merit
})

# DPRK, Soviet-pattern bars. The two orders exist in two classes whose bars
# differ by the centre stripe: one for the 1st class, two for the 2nd. Hero
# first, then the orders by seniority (Freedom and Independence above
# Soldier's Honour), the medal, and the war commemorative last.
RIBBONS.update({
    503007: Ribbon(503007),                       # Hero of the Republic
    503006: Ribbon(503006),                       # Freedom and Independence 1st
    503005: Ribbon(503005),                       # Freedom and Independence 2nd
    503004: Ribbon(503004),                       # Soldier's Honour 1st
    503003: Ribbon(503003),                       # Soldier's Honour 2nd
    503002: Ribbon(503002),                       # Military Merit Medal
    503008: Ribbon(503008),                       # Fatherland Liberation War 1950-1953
})

PRECEDENCE: Dict[int, int] = {aid: i for i, aid in enumerate(RIBBONS)}


def rack(award_ids) -> List[int]:
    """The ribbons a pilot wears, highest precedence first, one per ladder."""
    worn = sorted({a for a in award_ids if a in RIBBONS}, key=PRECEDENCE.get)
    seen: set = set()
    out = []
    for aid in worn:
        base = RIBBONS[aid].base
        if base in seen:
            continue
        seen.add(base)
        out += [aid] * RIBBONS[aid].repeat      # a repeat awarding is another bar
    return out


def rows(count: int, per_row: int = 3) -> List[int]:
    """Row sizes top to bottom: full rows of three, a short top row centred."""
    if count <= 0:
        return []
    first = count % per_row or per_row
    return [first] + [per_row] * ((count - first) // per_row)


# Three to a row is everyone's default, and never more than four. The Navy
# holds to three whatever the count; the Air Force and the Marine Corps
# widen once three would stack higher than they allow - the Air Force
# sooner, the Marines only on a really deep rack. See docs/NAVY_RACK.md
# and docs/ARMY_USAF_RACK.md.
MAX_ROWS_AT_THREE = {"usaf": 5, "usmc": 6}


def per_row_for(coat: Optional[str], count: int) -> int:
    limit = MAX_ROWS_AT_THREE.get(coat or "")
    if limit is not None and -(-count // 3) > limit:
        return 4
    return 3


class RibbonRenderer:
    """Composes one ribbon per award id and caches the PNG on disk."""

    def __init__(self, cache_dir: Path):
        # The revision is part of the path, so a change to the art or the
        # composition can never be served from a stale cache. (Note the Store
        # Python virtualises %LOCALAPPDATA% into its own Packages folder, so
        # "delete the cache" is not the reliable fix it looks like.)
        self.cache_dir = Path(cache_dir) / "ribbons" / f"v{REVISION}"
        self._art: Dict[str, object] = {}

    def _load(self, name: str):
        if name in self._art:
            return self._art[name]
        from PIL import Image
        source = {"star_silver_large": "star_silver", "star_silver_navy": "star_silver",
                  "star_bronze_navy": "star_bronze"}.get(name, name)
        path = ART / f"{source}.png"
        img = Image.open(path).convert("RGBA") if path.is_file() else None
        if img is None:
            logger.warning("Ribbon art missing: %s", path.name)
        self._art[name] = img
        return img

    def _device(self, name: str):
        """A device at regulation size: clusters levelled (they are worn
        horizontally, and the art may have been drawn at an angle), then
        every device scaled to its share of the bar. Done once and kept."""
        key = f"{name}@fit"
        if key in self._art:
            return self._art[key]
        img = self._load(name)
        if img is not None:
            from PIL import Image
            if name.startswith("olc"):
                img = _level(img)
            box = img.getbbox()
            if box:
                img = img.crop(box)
            kind = ("olc" if name.startswith("olc") else
                    "v" if name.startswith("v") else
                    "award_star" if name in BIG_STARS else
                    "star")
            if name in NAVY_STARS:
                # Korean War Navy/USMC stars are worn one point DOWN
                # (DEVICE_RULES.md 4, 5, 9); the art is drawn point-up.
                img = img.rotate(180)
            axis, share = DEVICE_SIZE[kind]
            target = share * (BAR[0] if axis == "w" else BAR[1])
            scale = target / (img.width if axis == "w" else img.height)
            size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
            img = img.resize(size, Image.LANCZOS)
        self._art[key] = img
        return img

    def png(self, award_id: int, naval: bool = False) -> Optional[bytes]:
        spec = RIBBONS.get(award_id)
        if spec is None:
            return None
        # A shared award's campaign stars differ by wearer, so the naval
        # rendering is a separate picture and a separate cache entry.
        out = self.cache_dir / ("navy" if naval else "") / f"{award_id}.png"
        if out.is_file():
            return out.read_bytes()
        data = self.compose(spec, naval)
        if data is not None:
            try:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(data)
            except OSError as exc:            # a read-only cache is not fatal
                logger.warning("Cannot cache ribbon %s: %s", award_id, exc)
        return data

    def compose(self, spec: Ribbon, naval: bool = False) -> Optional[bytes]:
        from PIL import Image
        bar = self._load(str(spec.base))
        if bar is None:
            return None
        size = GEOMETRY[geometry(spec.base)]
        if bar.size != size:
            bar = bar.resize(size, Image.LANCZOS)
        canvas = Image.new("RGBA", (size[0] + 2 * MARGIN, size[1] + 2 * MARGIN), (0, 0, 0, 0))
        canvas.alpha_composite(bar, (MARGIN, MARGIN))
        wanted = [NAVAL_STAR.get(n, n) for n in spec.devices] if naval else list(spec.devices)
        names = [n for n in wanted if self._device(n) is not None]
        devices = [self._device(n) for n in names]
        if devices:
            gap, width = fit_row([d.width for d in devices], BAR[0], DEVICE_GAP, DEVICE_GAP_TIGHT)
            x = MARGIN + row_origin(names, [d.width for d in devices], gap, BAR[0])
            for d in devices:
                y = MARGIN + (BAR[1] - d.height) // 2
                canvas.alpha_composite(d, (x, y))
                x += d.width + gap
        if spec.framed:
            frame = self._load("frame_gold")
            if frame is not None:
                canvas.alpha_composite(frame, (0, 0))
        buf = io.BytesIO()
        canvas.save(buf, "PNG", optimize=True)
        return buf.getvalue()


def _level(img):
    """Rotate a device so its long axis is horizontal, from the alpha's
    principal axis (pure Python over the alpha band: a device is a few
    thousand pixels, and this runs once per device per process), and re-fit
    it to its ink. Art that is already level within 3 degrees is untouched."""
    from PIL import Image
    alpha = img.getchannel("A")
    w, h = alpha.size
    data = alpha.getdata()
    n = sx = sy = 0.0
    pts = []
    for i, a in enumerate(data):
        if a > 40:
            x, y = i % w, i // w
            pts.append((x, y, a))
            n += a
            sx += a * x
            sy += a * y
    if len(pts) < 10:
        return img
    cx, cy = sx / n, sy / n
    sxx = syy = sxy = 0.0
    for x, y, a in pts:
        dx, dy = x - cx, y - cy
        sxx += a * dx * dx
        syy += a * dy * dy
        sxy += a * dx * dy
    angle = 0.5 * math.degrees(math.atan2(2 * sxy, sxx - syy))
    if abs(angle) < 3:
        return img
    # PIL rotates counter-clockwise for positive angles, image y points down.
    big = img.resize((img.width * 4, img.height * 4), Image.LANCZOS)
    turned = big.rotate(angle, resample=Image.BICUBIC, expand=True)
    box = turned.getbbox()
    if box:
        turned = turned.crop(box)
    scale = min(h / turned.height, img.width * 1.4 / turned.width)
    size = (max(1, round(turned.width * scale)), max(1, round(turned.height * scale)))
    return turned.resize(size, Image.LANCZOS)
