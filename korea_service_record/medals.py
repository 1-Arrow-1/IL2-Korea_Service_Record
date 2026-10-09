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
REVISION = 33

# A device pinned to the ribbon stands a little off the cloth: a soft dark
# copy of its outline, down and slightly right, under it. Without one the
# clusters looked printed on. In drape pixels (the drape is 224 wide).
DEVICE_SHADOW_OFFSET = (1, 2)
DEVICE_SHADOW_BLUR = 1.6
DEVICE_SHADOW_ALPHA = 0.55


def _device_shadow(device):
    """The shadow for one device, and where it sits relative to the device."""
    from PIL import Image, ImageFilter
    pad = 4
    alpha = device.getchannel("A").point(lambda v: round(v * DEVICE_SHADOW_ALPHA))
    shadow = Image.new("RGBA", (device.width + 2 * pad, device.height + 2 * pad), (25, 16, 6, 0))
    mask = Image.new("L", shadow.size, 0)
    mask.paste(alpha, (pad, pad))
    shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(DEVICE_SHADOW_BLUR)))
    return shadow, (DEVICE_SHADOW_OFFSET[0] - pad, DEVICE_SHADOW_OFFSET[1] - pad)

# --- US: drawn art -----------------------------------------------------------
# Every base medal is drawn 224 px wide - the drape is 1 3/8 inch, the same
# width as a ribbon bar, so a device is simply the bar's device at 224/440 -
# and 474 px tall, the top of the drape at the top edge. The straight part of
# the drape runs 185 px before it tapers to the suspension ring; devices are
# centred on that.
DRAPE = (224, 474)
DRAPE_LENGTH = 185
DEVICE_SCALE = DRAPE[0] / ribbons.BAR[0]
# A cluster on the suspension ribbon is the 13/32" one, not the bar's 5/16"
# (DEVICE_RULES.md 2); stars are the same size on both. Four clusters go
# three in a row with the fourth centred above them, never four across.
OLC_MEDAL_SCALE = (13 / 32) / (5 / 16)
DEVICE_GAP = round(0.02 * DRAPE[0])
DEVICE_GAP_TIGHT = round(0.015 * DRAPE[0])

# Worn around the neck, not on the bar.
NECK = (601026, 601041, 602027, 602038)
# A repeat award falls back to the base decoration's neck art unless it has
# its own (neck_602038.png carries the Navy's gold star on the pad).
NECK_ART = {601041: 601026, 602038: 602027}
# neck_601041.png and neck_602038.png carry the repeat device on the pad -
# a bronze cluster for the Air Force, a gold star for the naval services -
# so those ids find their own art before this fallback applies.

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
# Loose Soviet mounted-medal art uses one full-resolution canvas.  It is
# reduced to the atlas pieces' physical scale on the coat, while the
# shadowbox keeps enough source resolution for its larger display.
SOVIET_MOUNT_CANVAS = (232, 458)
SOVIET_WWII = {501050, 501051, 501052, 501053, 501054}
# Orders and medals on a pentagonal ribbon mount: the left breast.
MOUNTED = {501024, 501016, 501018, 501020, 501002, 501004,      # USSR
           *SOVIET_WWII,
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
        if award_id in SOVIET_WWII:
            return round(SOVIET_MOUNT_CANVAS[0] * TILE_SCALE /
                         COAT_PX[coat] * 100, 3)
        from PIL import Image
        with Image.open(own) as img:
            return round(img.width / COAT_PX[coat] * 100, 3)
    sheet = icons.sheet("award") if icons is not None else None
    crop = sheet.crops.get(f"award{award_id}") if sheet else None
    if crop is None:
        return None
    return round((crop.box[2] - crop.box[0]) * TILE_SCALE / COAT_PX[coat] * 100, 3)


def neck_url(award_id: Optional[int], coat: Optional[str] = None) -> Optional[str]:
    """The neck decoration's picture: own art (neck_<id>.png, the ribbon as
    it goes round the collar) where drawn, else the game's atlas tile."""
    if award_id is None:
        return None
    if coat == "usmc" and award_id in (602027, 602038):
        # The neck decoration is only ever drawn in full dress, which for a
        # Marine is Blue Dress "A"; the green coat's overlay stays for the
        # case where no blue art exists.
        blue = ART / f"neck_{award_id}_USMC_BD.png"
        if blue.is_file():
            return f"/static/images/medals/{blue.name}?v={REVISION}"
        own = ART.parent / f"usmc_MoH_w_collar_overlay_{award_id}.png"
        name = own.name if own.is_file() else "usmc_MoH_w_collar_overlay.png"
        return f"/static/images/{name}?v={REVISION}"
    for art_id in (award_id, NECK_ART.get(award_id, award_id)):
        if (ART / f"neck_{art_id}.png").is_file():
            return f"/static/images/medals/neck_{art_id}.png?v={REVISION}"
    return f"/api/icon/award/{award_id}"


def rows(count: int, per_row: int = 4) -> List[int]:
    """Row sizes top to bottom: full rows, a short top row centred."""
    return ribbons.rows(count, per_row)


# The Navy's own distribution of full-size medals over rows, top to bottom
# (docs/NAVY_RACK.md 3). Not a formula: 13 is 3/5/5 where 14 is 4/5/5, and
# 21 opens with a row of two. Beyond 25 the table runs out and rows of five
# carry the rest.
NAVY_ROWS = {
    1: [1], 2: [2], 3: [3], 4: [4], 5: [5],
    6: [3, 3], 7: [3, 4], 8: [4, 4], 9: [4, 5], 10: [5, 5],
    11: [3, 4, 4], 12: [4, 4, 4], 13: [3, 5, 5], 14: [4, 5, 5], 15: [5, 5, 5],
    16: [4, 4, 4, 4], 17: [3, 4, 5, 5], 18: [3, 5, 5, 5], 19: [4, 5, 5, 5],
    20: [5, 5, 5, 5],
    21: [2, 4, 5, 5, 5], 22: [3, 4, 5, 5, 5], 23: [3, 5, 5, 5, 5],
    24: [4, 5, 5, 5, 5], 25: [5, 5, 5, 5, 5],
}


# The Air Force normally mounts three full-size medals to a row. A deep rack
# may overlap four or five on a bar, but never opens a fifth row: six remains
# two rows of three, 13-16 use four-wide bars, and 17-20 use five-wide bars.
# Soviet-pattern coats keep five.
MAX_USAF_MEDAL_ROWS = 4


def rows_for(coat: Optional[str], count: int) -> List[int]:
    """The row sizes for a breast rack of full-size medals, by service."""
    if coat in ("usnavy", "usmc"):
        return navy_rows(count)
    if coat in ("sov", "dprk"):
        return rows(count, 5)
    per = 3
    while per < 5 and -(-count // per) > MAX_USAF_MEDAL_ROWS:
        per += 1
    return rows(count, per)


def navy_rows(count: int) -> List[int]:
    """Navy row distribution for a breast rack of `count` full-size medals.
    The Medal of Honor (neck) and ribbon-only unit awards are not in it."""
    if count <= 0:
        return []
    if count in NAVY_ROWS:
        return NAVY_ROWS[count]
    first = count % 5 or 5
    return [first] + [5] * ((count - first) // 5)


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


# --- the roll of the drape -------------------------------------------------
# The drawn bases are woven but flat. A ribbon bar bows over its mount and
# so shades down its height (ribbons.roll); a drape hangs and bows across
# its width, and it narrows through the chevron, so the curve has to follow
# each row's own edges rather than the canvas. It fades out above the waist,
# which leaves the medal exactly as painted - nothing below that row is
# touched at all.
DRAPE_CREST = 0.42     # where the cloth is brightest, across its own width
DRAPE_AMP = 0.22       # how far it falls to the selvedges
DRAPE_RIM = 0.16       # extra darkening at the very edges
DRAPE_SHEEN = 0.08     # a soft highlight along the crest
DRAPE_FADE = 0.18      # the share of the drop over which it fades to nothing

# The waist - the suspension ring or clasp - is looked for between these
# fractions of the height. Above is cloth, below is medal.
WAIST_BAND = (0.30, 0.72)


def waist(alpha) -> int:
    """The row where the ribbon hands the weight to the medal."""
    import numpy as np

    wide = (alpha > 100).sum(axis=1)
    lo, hi = (int(len(wide) * f) for f in WAIST_BAND)
    return lo + int(np.argmin(wide[lo:hi]))


def roll(img):
    """Light the drape as hanging cloth, leaving the medal untouched."""
    import numpy as np
    from PIL import Image

    a = np.asarray(img.convert("RGBA")).astype(float)
    al = a[..., 3]
    h, w = al.shape
    cut = waist(al)
    opaque = al > 100
    if not opaque.any():
        return img

    # each row's own span, so the chevron stays lit as it narrows
    left = np.argmax(opaque, axis=1)
    right = w - 1 - np.argmax(opaque[:, ::-1], axis=1)
    span = np.maximum(right - left, 1)[:, None]
    u = np.clip((np.arange(w)[None, :] - left[:, None]) / span, 0.0, 1.0)

    v = np.where(u < DRAPE_CREST, (DRAPE_CREST - u) / DRAPE_CREST,
                 (u - DRAPE_CREST) / (1.0 - DRAPE_CREST))
    k = 1.0 - DRAPE_AMP * v ** 2
    k *= 1.0 - DRAPE_RIM * (1.0 - np.clip(np.minimum(u, 1 - u) / 0.08, 0, 1))
    k *= 1.0 + DRAPE_SHEEN * np.exp(-((u - 0.33) / 0.12) ** 2)

    y = np.arange(h)[:, None]
    ramp = max(cut * DRAPE_FADE, 1.0)
    strength = np.where(y >= cut, 0.0, np.clip((cut - y) / ramp, 0.0, 1.0))
    k = 1.0 + (k - 1.0) * strength

    out = a.copy()
    out[..., :3] = np.clip(a[..., :3] * k[..., None], 0, 255)
    return Image.fromarray(out.astype(np.uint8), "RGBA")


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
        else:
            if img.size != DRAPE:
                img = img.resize(DRAPE, Image.LANCZOS)
            # Shaded once per base, not per rung: the lighting is the same
            # whatever devices end up on the ribbon.
            img = roll(img)
        self._art[base] = img
        return img

    def png(self, award_id: int, naval: bool = False) -> Optional[bytes]:
        # Badges and stripes have no ribbon and so no Ribbon spec.
        spec = ribbons.RIBBONS.get(award_id)
        if award_id not in ATLAS and (spec is None or spec.base not in DRAWN):
            return None
        out = self.cache_dir / ("navy" if naval else "") / f"{award_id}.png"
        if out.is_file():
            return out.read_bytes()
        own = ART / f"{award_id}.png"
        if award_id in SOVIET_WWII and own.is_file():
            data = self._soviet_mounted(own)
        elif award_id in ATLAS and own.is_file():
            data = own.read_bytes()             # drawn for this coat: used as it is
        elif award_id in ATLAS:
            data = self.from_atlas(award_id)
        else:
            data = self.compose(spec, naval)
        if data is not None:
            try:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(data)
            except OSError as exc:
                logger.warning("Cannot cache medal %s: %s", award_id, exc)
        return data

    @staticmethod
    def _soviet_mounted(path: Path) -> bytes:
        """Fit supplied Soviet mounted-medal art to its common canvas."""
        from PIL import Image

        with Image.open(path) as source:
            image = source.convert("RGBA")
        if image.size == SOVIET_MOUNT_CANVAS:
            return path.read_bytes()
        image.thumbnail(SOVIET_MOUNT_CANVAS, Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", SOVIET_MOUNT_CANVAS, (0, 0, 0, 0))
        canvas.alpha_composite(image, ((SOVIET_MOUNT_CANVAS[0] - image.width) // 2, 0))
        out = io.BytesIO()
        canvas.save(out, "PNG", optimize=True)
        return out.getvalue()

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

    def compose(self, spec: ribbons.Ribbon, naval: bool = False) -> Optional[bytes]:
        from PIL import Image
        base = self._base(spec.base)
        if base is None:
            return None
        canvas = base.copy()
        # The bar's devices scaled with the drape, clusters to their larger
        # medal size (DEVICE_RULES.md 2); rows never shrunk (10).
        names, devices = [], []
        for n in ([ribbons.NAVAL_STAR.get(d, d) for d in spec.devices] if naval else spec.devices):
            d = self.ribbons._device(n)
            if d is None:
                continue
            k = DEVICE_SCALE * (OLC_MEDAL_SCALE if n.startswith("olc") else 1.0)
            names.append(n)
            devices.append(d.resize((max(1, round(d.width * k)), max(1, round(d.height * k))), Image.LANCZOS))
        if devices:
            # Four or more clusters, and nothing else: three across, the
            # rest centred above. Everything else is one centred row.
            if len(devices) >= 4 and all(n.startswith("olc") for n in names):
                rows = [(names[-3:], devices[-3:]), (names[:-3], devices[:-3])]
            else:
                rows = [(names, devices)]
            vgap = DEVICE_GAP
            total_h = sum(max(d.height for d in r) for _, r in rows) + vgap * (len(rows) - 1)
            y = (DRAPE_LENGTH - total_h) // 2
            for row_names, row in reversed(rows):
                # bottom row is the main one; each row placed on its own
                rh = max(d.height for d in row)
                gap, width = ribbons.fit_row([d.width for d in row], DRAPE[0], DEVICE_GAP, DEVICE_GAP_TIGHT)
                x = ribbons.row_origin(row_names, [d.width for d in row], gap, DRAPE[0])
                for d in row:
                    at = (x, y + (rh - d.height) // 2)
                    shadow, offset = _device_shadow(d)
                    sx, sy = at[0] + offset[0], at[1] + offset[1]
                    # alpha_composite refuses a negative destination; a
                    # device at the ribbon's edge loses that strip of padding
                    canvas.alpha_composite(shadow, (max(0, sx), max(0, sy)),
                                           (max(0, -sx), max(0, -sy)))
                    canvas.alpha_composite(d, at)
                    x += d.width + gap
                y += rh + vgap
        buf = io.BytesIO()
        canvas.save(buf, "PNG", optimize=True)
        return buf.getvalue()
