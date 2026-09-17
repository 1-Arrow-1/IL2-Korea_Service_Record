"""
Ribbon rack: the service ribbons a pilot wears on the tunic, composed from
the mod's own art rather than the game's medal atlases.

    static/images/ribbons/<base award>.png     bar, no devices (440x120 US, 420x140 Soviet pattern)
    static/images/ribbons/olc_bronze.png ...   devices, any size (scaled down to the bar)
    static/images/ribbons/frame_gold.png       480x160, the unit-citation frame

Every award id the USAF ladders can hand out maps to one base ribbon and the
devices worn on it: oak leaf clusters (a silver one standing for five
bronze), the bronze V of a Bronze Star awarded for valour, and the service
stars of the Korean Service Medal (a silver one for five bronze). Twin ids
that the awards.cfg needs for one rung (601059/601061, 601060/601062) map to
the same composition, so the rack never shows a rung twice.

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
REVISION = 9
# US bars are 1 3/8 x 3/8 inch (11:3); Soviet-pattern bars (USSR, DPRK) are
# 24 x 8 mm (3:1). Each sits centred on a canvas 20 px bigger all round, so a
# unit citation's frame can overhang without changing the grid.
MARGIN = 20
GEOMETRY = {"us": (440, 120), "sov": (420, 140)}
BAR = GEOMETRY["us"]
CANVAS = (BAR[0] + 2 * MARGIN, BAR[1] + 2 * MARGIN)

DEVICE_GAP = 6
DEVICE_INSET = 10   # the least ribbon left showing beside a full row of devices
# Regulation device sizes on a 1 3/8 x 3/8 inch bar, as a fraction of the bar:
# an oak leaf cluster is 5/16 inch wide, the V 1/4 inch tall, a service star
# 3/16 inch. Every device is drawn at the same scale on every ribbon - a
# four-cluster bar must not carry smaller clusters than a three-cluster one -
# and regulation size is exactly what fits four clusters with the gap and
# inset above (4 x 100 + 3 x 6 = 418 of 420). The shrink in compose() is
# only a guard against art that arrives with more padding than expected.
OVERSCALE = 1.0
DEVICE_SIZE = {"olc": ("w", OVERSCALE * 5 / 16 / (11 / 8)), "v": ("h", OVERSCALE * 1 / 4 / (3 / 8)),
               "star": ("h", OVERSCALE * 3 / 16 / (3 / 8))}


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
    framed: bool = False      # unit citation
    repeat: int = 1           # Soviet repeat awardings: one more identical bar each

    @property
    def devices(self) -> List[str]:
        """Device files left to right as worn: V, then silver before bronze."""
        out: List[str] = []
        if self.valour:
            out.append("v_device")
        out += ["olc_silver"] * self.olc_silver + ["olc_bronze"] * self.olc_bronze
        out += ["star_silver"] * self.star_silver + ["star_bronze"] * self.star_bronze
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
RIBBONS.update(_ladder(601043, [601043, 601047, 601048, 601049], framed=True))      # ROK PUC
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
        path = ART / f"{name}.png"
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
            axis, share = DEVICE_SIZE["olc" if name.startswith("olc") else
                                      "v" if name.startswith("v") else "star"]
            target = share * (BAR[0] if axis == "w" else BAR[1])
            scale = target / (img.width if axis == "w" else img.height)
            size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
            img = img.resize(size, Image.LANCZOS)
        self._art[key] = img
        return img

    def png(self, award_id: int) -> Optional[bytes]:
        spec = RIBBONS.get(award_id)
        if spec is None:
            return None
        out = self.cache_dir / f"{award_id}.png"
        if out.is_file():
            return out.read_bytes()
        data = self.compose(spec)
        if data is not None:
            try:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(data)
            except OSError as exc:            # a read-only cache is not fatal
                logger.warning("Cannot cache ribbon %s: %s", award_id, exc)
        return data

    def compose(self, spec: Ribbon) -> Optional[bytes]:
        from PIL import Image
        bar = self._load(str(spec.base))
        if bar is None:
            return None
        size = GEOMETRY[geometry(spec.base)]
        if bar.size != size:
            bar = bar.resize(size, Image.LANCZOS)
        canvas = Image.new("RGBA", (size[0] + 2 * MARGIN, size[1] + 2 * MARGIN), (0, 0, 0, 0))
        canvas.alpha_composite(bar, (MARGIN, MARGIN))
        devices = [self._device(n) for n in spec.devices]
        devices = [d for d in devices if d is not None]
        if devices:
            gap = DEVICE_GAP
            width = sum(d.width for d in devices) + gap * (len(devices) - 1)
            # A full row (four clusters, or a V with two) is mounted tight
            # and inside the ribbon: shrink the set together to fit with a
            # small inset rather than let it hang over the edges.
            usable = BAR[0] - 2 * DEVICE_INSET
            if width > usable:
                scale = usable / width
                devices = [d.resize((max(1, round(d.width * scale)),
                                     max(1, round(d.height * scale))), Image.LANCZOS)
                           for d in devices]
                gap = max(2, round(gap * scale))
                width = sum(d.width for d in devices) + gap * (len(devices) - 1)
            x = MARGIN + (BAR[0] - width) // 2
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
