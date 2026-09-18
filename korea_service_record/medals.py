"""
Full-size medals, for the coat in full dress.

The ribbon rack (ribbons.py) is what a man wore every day; on the formal
occasions he wore the awards themselves. This module composes those.

US awards: one PNG per base medal (drape plus pendant, drawn to a common
scale, no devices) with the same clusters, V and stars as the ribbon, at the
same regulation size, on the drape. Unit citations (DUC, ROK PUC) are
ribbon-only and stay on the right breast; the Medal of Honor is a neck
decoration and goes to the collar.

Soviet-pattern awards (USSR, DPRK): the game's own atlas tiles, which carry
no devices - a second Red Banner is a second order with a numeral, and has
its own tile. They are brought to one physical scale here, because the game
drew them at whatever size filled the tile. Three kinds of wear: orders and
medals on pentagonal ribbon mounts (left breast), screw-back orders with no
ribbon at all (pinned to the right breast), and the Gold Star of a Hero,
worn in kind above everything even with ribbon bars.
"""

import io
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import ribbons

logger = logging.getLogger(__name__)

ART = Path(__file__).resolve().parent / "static" / "images" / "medals"
# Bump whenever the composition or the art changes; it is part of the URLs.
REVISION = 4

# --- US: drawn art -----------------------------------------------------------
# Every base medal is drawn 224 px wide - the drape is 1 3/8 inch, the same
# width as a ribbon bar, so a device is simply the bar's device at 224/440 -
# and 474 px tall, the top of the drape at the top edge. The straight part of
# the drape runs 185 px before it tapers to the suspension ring; devices are
# centred on that.
DRAPE = (224, 474)
DRAPE_LENGTH = 185
DEVICE_SCALE = DRAPE[0] / ribbons.BAR[0]

# Worn around the neck, not on the bar.
NECK = (601026, 601041)

# Awards with drawn art: the base ids with a file in the folder.
DRAWN = {int(p.stem) for p in ART.glob("[0-9]*.png") if p.stem.isdigit()}

# --- Soviet pattern: atlas tiles ----------------------------------------------
# The game's tiles are used as they are and scaled on the coat: the Soviet
# coat photograph (1086 px wide) takes every tile at 42%, which is the scale
# the reference mock-up was laid out at. Pieces drawn for the coat (a file
# <id>.png in the art folder, e.g. the Red Star and Nevsky with the coat's
# perspective in them) are already at coat scale, 1:1.
COAT_PX = {"sov": 1086, "dprk": 1122}
TILE_SCALE = 0.42
# Orders and medals on a pentagonal ribbon mount: the left breast.
MOUNTED = {501024, 501016, 501018, 501020, 501002, 501004,      # USSR
           503002, 503008}                                       # DPRK
# Screw-back orders, pinned without a ribbon to the right breast.
PINNED = {501014, 501012, 501006,                                # Suvorov, Nevsky, Red Star
          503006, 503005, 503004, 503003}                        # DPRK orders
# The Hero's star on its small mount, worn in kind with every dress.
HERO = {501022, 503007}
# Qualification badges, right breast: only the highest held is worn.
WINGS = (501049, 501048, 501047, 501046,      # 1st, 2nd, 3rd class, pilot
         503001)                              # DPRK pilot badge
# Wound stripes, right breast above everything, side by side.
STRIPES = (501038, 501037)                    # severe (yellow), light (red)
ATLAS = MOUNTED | PINNED | HERO | set(WINGS) | set(STRIPES)


def wear(award_ids: Iterable[int]) -> Dict[str, Any]:
    """
    What is worn in kind, from the awards held: the same one-per-ladder rule
    and precedence as the ribbon rack, then sorted into where it goes.
      bar      medals on the breast bar (US drape or Soviet mount), in order
      neck     the neck decoration, or None
      pinned   screw-back orders for the right breast, in order
      hero     the Gold Star, or None
      wings    the highest qualification badge, or None
      stripes  wound stripes, severe first
    A Soviet repeat awarding is a separate order: the third Red Banner puts
    three orders on the bar, each its own tile.
    """
    held = set(award_ids)
    worn = ribbons.rack(held)
    out: Dict[str, Any] = {"bar": [], "neck": None, "pinned": [], "hero": None,
                           "wings": next((w for w in WINGS if w in held), None),
                           "stripes": [s for s in STRIPES if s in held]}
    seen = set()
    for aid in worn:
        if aid in seen:
            continue
        seen.add(aid)
        spec = ribbons.RIBBONS[aid]
        if aid in NECK:
            out["neck"] = out["neck"] or aid
        elif aid in HERO:
            out["hero"] = out["hero"] or aid
        elif aid in PINNED:
            out["pinned"].append(aid)
        elif spec.repeat > 1:
            out["bar"] += sorted((r for r, s in ribbons.RIBBONS.items()
                                  if s.base == spec.base and s.repeat <= spec.repeat and r in ATLAS),
                                 key=lambda r: ribbons.RIBBONS[r].repeat)
        elif aid in ATLAS or spec.base in DRAWN:
            out["bar"].append(aid)
    return out


def width_pct(icons, award_id: int, coat: str) -> Optional[float]:
    """The width of an atlas-drawn piece as a percentage of the coat's width,
    for the page to size it by; None for the drawn (US) medals, which the
    stylesheet sizes."""
    if award_id not in ATLAS:
        return None
    own = ART / f"{award_id}.png"
    if own.is_file():
        from PIL import Image
        with Image.open(own) as img:
            return round(img.width / COAT_PX[coat] * 100, 3)
    sheet = icons.sheet("award") if icons is not None else None
    crop = sheet.crops.get(f"award{award_id}") if sheet else None
    if crop is None:
        return None
    return round((crop.box[2] - crop.box[0]) * TILE_SCALE / COAT_PX[coat] * 100, 3)


def neck_url(award_id: Optional[int]) -> Optional[str]:
    """The neck decoration's picture: own art (neck_<id>.png, the ribbon as
    it goes round the collar) where drawn, else the game's atlas tile."""
    if award_id is None:
        return None
    if (ART / f"neck_{award_id}.png").is_file():
        return f"/static/images/medals/neck_{award_id}.png?v={REVISION}"
    return f"/api/icon/award/{award_id}"


def rows(count: int, per_row: int = 4) -> List[int]:
    """Row sizes top to bottom: full rows, a short top row centred."""
    return ribbons.rows(count, per_row)


def _widest(img) -> int:
    """The widest opaque span of the image, in px."""
    alpha = img.getchannel("A")
    w, h = alpha.size
    px = alpha.load()
    best = 0
    for y in range(0, h, 2):
        xs = [x for x in range(w) if px[x, y] > 128]
        if xs:
            best = max(best, xs[-1] - xs[0] + 1)
    return best


class MedalRenderer:
    """Composes one medal per award id and caches the PNG on disk."""

    def __init__(self, cache_dir: Path, ribbon_renderer: ribbons.RibbonRenderer, icons=None):
        self.cache_dir = Path(cache_dir) / "medals" / f"v{REVISION}"
        self.ribbons = ribbon_renderer
        self.icons = icons
        self._art: dict = {}

    def _base(self, base: int):
        if base in self._art:
            return self._art[base]
        from PIL import Image
        path = ART / f"{base}.png"
        img = Image.open(path).convert("RGBA") if path.is_file() else None
        if img is None:
            logger.warning("Medal art missing: %s", path.name)
        elif img.size != DRAPE:
            img = img.resize(DRAPE, Image.LANCZOS)
        self._art[base] = img
        return img

    def png(self, award_id: int) -> Optional[bytes]:
        # Badges and stripes have no ribbon and so no Ribbon spec.
        spec = ribbons.RIBBONS.get(award_id)
        if award_id not in ATLAS and (spec is None or spec.base not in DRAWN):
            return None
        out = self.cache_dir / f"{award_id}.png"
        if out.is_file():
            return out.read_bytes()
        own = ART / f"{award_id}.png"
        if award_id in ATLAS and own.is_file():
            data = own.read_bytes()             # drawn for this coat: used as it is
        elif award_id in ATLAS:
            data = self.from_atlas(award_id)
        else:
            data = self.compose(spec)
        if data is not None:
            try:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(data)
            except OSError as exc:
                logger.warning("Cannot cache medal %s: %s", award_id, exc)
        return data

    def from_atlas(self, award_id: int) -> Optional[bytes]:
        """A Soviet-pattern piece: the game's tile as it is - the page scales
        it (TILE_SCALE), and width_pct() sizes it from the same tile."""
        from PIL import Image
        if self.icons is None:
            return None
        raw = self.icons.png("award", str(award_id))
        if raw is None:
            return None
        tile = Image.open(io.BytesIO(raw)).convert("RGBA")
        buf = io.BytesIO()
        tile.save(buf, "PNG", optimize=True)
        return buf.getvalue()

    def compose(self, spec: ribbons.Ribbon) -> Optional[bytes]:
        from PIL import Image
        base = self._base(spec.base)
        if base is None:
            return None
        canvas = base.copy()
        # The bar's devices, at the bar's regulation size, scaled with the
        # drape; a full row is shrunk together to fit, as on the bar.
        devices = [self.ribbons._device(n) for n in spec.devices]
        devices = [d.resize((max(1, round(d.width * DEVICE_SCALE)),
                             max(1, round(d.height * DEVICE_SCALE))), Image.LANCZOS)
                   for d in devices if d is not None]
        if devices:
            gap = max(2, round(ribbons.DEVICE_GAP * DEVICE_SCALE))
            width = sum(d.width for d in devices) + gap * (len(devices) - 1)
            usable = DRAPE[0] - 2 * round(ribbons.DEVICE_INSET * DEVICE_SCALE)
            if width > usable:
                scale = usable / width
                devices = [d.resize((max(1, round(d.width * scale)),
                                     max(1, round(d.height * scale))), Image.LANCZOS)
                           for d in devices]
                gap = max(2, round(gap * scale))
                width = sum(d.width for d in devices) + gap * (len(devices) - 1)
            x = (DRAPE[0] - width) // 2
            for d in devices:
                canvas.alpha_composite(d, (x, (DRAPE_LENGTH - d.height) // 2))
                x += d.width + gap
        buf = io.BytesIO()
        canvas.save(buf, "PNG", optimize=True)
        return buf.getvalue()
