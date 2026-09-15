"""
The map: the game's own briefing chart, and where things on it are.

Coordinates
-----------
Every position the career keeps - route waypoints, targets, kills - is in
world metres on a 499,200 m square. ``x`` runs north from the south edge,
``z`` east from the west edge, ``y`` is altitude. Settled against a fixed
point: the game's airfield file for K-16 Seoul is named ``!x102349z280779``,
and the map overlay puts the K-16 label at exactly ``(z / 25, (499200 - x)
/ 25)`` pixels on its 19,968-px canvas. So on any raster at ``m`` metres per
pixel a point lands at ``(z / m, (WORLD - x) / m)``.

Tiles
-----
``nsdata/assets/maptiles/korea`` (Interface.gtp) is the chart as a pyramid:
level "01" is 8x8 tiles of 1024 px, "02" 16x16, "04" 32x32 - 61, 30 and 15 m
per pixel - named ``<row>_<col>.dds`` with row 1 at the top. The map has a
30 km border of paper round the playable area, which the tiles include.
Nothing is shipped: tiles are read from the player's own installation through
the asset resolver and converted to JPEG once, into the same cache the icons
use.

Overlay
-------
``overlay.xaml`` holds every label and marker the game draws over the chart:
airfields (``af<name>`` keys, 40), towns in two sizes (~900), rail stations,
mines and camps, all as canvas positions at 25 m/px. Names come from
``airfields.locale=<lang>.json`` / ``cities.locale=<lang>.json`` beside it,
which the game ships in English, Russian and Chinese only; the other
languages fall back to English.
"""

import io
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional

from .gamedata import loads_lenient

logger = logging.getLogger(__name__)

WORLD_M = 499200.0
TILES = "nsdata/assets/maptiles/korea"
TILE_PX = 1024
BASE_TILES = 8                       # level "01"
LEVELS = {0: "01", 1: "02", 2: "04"}  # zoom -> folder; tiles per side = 8 << zoom
OVERLAY_M_PER_PX = 25.0
BORDER_M = 30000.0                   # paper margin round the playable area

# Route waypoint types, from the first mission of a real career: the take-off
# and landing points are the airfield and carry its ground altitude.
WAYPOINT_TAKEOFF, WAYPOINT_ROUTE, WAYPOINT_TARGET, WAYPOINT_LANDING = 0, 1, 2, 3

OVERLAY_KINDS = {
    "airfields-icon": "airfield",
    "cities-size_2": "city",
    "cities-size_other": "town",
    "rw_stations-icon": "station",
    "mines-icon": "mine",
    "military_camp-icon": "camp",
}
OVERLAY_LANGS = ("eng", "rus", "chs")


def m_per_px(zoom: int) -> float:
    return WORLD_M / (TILE_PX * (BASE_TILES << zoom))


def to_px(x_m: float, z_m: float, zoom: int) -> Dict[str, float]:
    m = m_per_px(zoom)
    return {"px": z_m / m, "py": (WORLD_M - x_m) / m}


def parse_route(raw: Optional[str]) -> List[Dict[str, Any]]:
    """mission.route -> [{type, x, z, alt, speed}] in flight order."""
    if not raw:
        return []
    text = urllib.parse.unquote(raw)
    head, _, body = text.partition("|")
    cols = head.split(",")
    out = []
    for rec in body.split("|"):
        vals = rec.split(",")
        if len(vals) != len(cols):
            continue
        row = dict(zip(cols, vals))
        try:
            out.append({
                "type": int(row.get("type", "1")),
                "x": float(row["x"]), "z": float(row["z"]),
                "alt": float(row.get("y", "0")),
                "speed": float(row.get("speed", "0")),
            })
        except (KeyError, ValueError):
            continue
    return out


def parse_point(raw: Optional[str]) -> Optional[Dict[str, float]]:
    """target.point 'ori=193&x=145371&y=81&z=352285' -> {x, z, alt}."""
    if not raw:
        return None
    try:
        fields = dict(p.split("=", 1) for p in urllib.parse.unquote(raw).split("&") if "=" in p)
        return {"x": float(fields["x"]), "z": float(fields["z"]),
                "alt": float(fields.get("y", "0"))}
    except (KeyError, ValueError):
        return None


class MapTiles:
    """Tiles of the game's chart as JPEG, converted on first use."""

    def __init__(self, resolver):
        self.resolver = resolver

    def tile(self, zoom: int, row: int, col: int) -> Optional[bytes]:
        """
        A 1024-px JPEG tile at ``zoom``: the game's own levels for 0..2,
        and for -1 and -2 a tile composed from level 0, so the theatre
        overview is four small tiles rather than sixty-four large ones.
        """
        if zoom < 0:
            return self._composed(zoom, row, col)
        level = LEVELS.get(zoom)
        side = BASE_TILES << zoom if level else 0
        if level is None or not (0 <= row < side and 0 <= col < side):
            return None
        vpath = f"{TILES}/{level}/{row + 1:02d}_{col + 1:02d}.dds"
        cached = self.resolver._cache_path(vpath).with_suffix(".jpg")
        if cached.is_file():
            try:
                return cached.read_bytes()
            except OSError:
                pass
        image = self._image(vpath)
        if image is None:
            return None
        data = self._jpeg(image)
        self.resolver._write_cache(cached, data)
        return data

    def _image(self, vpath: str):
        # Straight from the archive: caching the 512 KB DDS beside the 150 KB
        # JPEG would double the footprint, and a full zoom of the finest
        # level is 1,024 tiles.
        blob = self.resolver.read(vpath, use_cache=False)
        if blob is None:
            return None
        try:
            from PIL import Image
            return Image.open(io.BytesIO(blob)).convert("RGB")
        except Exception as exc:                       # noqa: BLE001
            logger.warning("Cannot decode map tile %s: %s", vpath, exc)
            return None

    @staticmethod
    def _jpeg(image) -> bytes:
        buf = io.BytesIO()
        image.save(buf, "JPEG", quality=82, optimize=True)
        return buf.getvalue()

    def _composed(self, zoom: int, row: int, col: int) -> Optional[bytes]:
        k = -zoom
        if k > 3:
            return None
        per = 1 << k                                   # level-0 tiles per side
        side = BASE_TILES >> k
        if not (0 <= row < side and 0 <= col < side):
            return None
        cached = self.resolver._cache_path(f"{TILES}/z{zoom}/{row + 1:02d}_{col + 1:02d}.jpg")
        if cached.is_file():
            try:
                return cached.read_bytes()
            except OSError:
                pass
        from PIL import Image
        cell = TILE_PX // per
        out = Image.new("RGB", (TILE_PX, TILE_PX))
        for dr in range(per):
            for dc in range(per):
                r0, c0 = row * per + dr, col * per + dc
                image = self._image(f"{TILES}/01/{r0 + 1:02d}_{c0 + 1:02d}.dds")
                if image is None:
                    return None
                out.paste(image.resize((cell, cell), Image.LANCZOS), (dc * cell, dr * cell))
        data = self._jpeg(out)
        self.resolver._write_cache(cached, data)
        return data


class Overlay:
    """The chart's labels and markers, positioned in world metres."""

    _CONTROL = re.compile(
        r'<Control Style="\{StaticResource ([^}]+)\}" Canvas\.Left="([\d.]+)" Canvas\.Top="([\d.]+)"')
    _LABEL = re.compile(
        r'<TextBlock Text="\{app:Localize ([^}]+)\}" Canvas\.Left="([\d.]+)" Canvas\.Top="([\d.]+)"')

    def __init__(self, resolver, lang: str = "eng"):
        self.resolver = resolver
        self.lang = lang if lang in OVERLAY_LANGS else "eng"
        self._features: Optional[List[Dict[str, Any]]] = None

    def _names(self, stem: str) -> Dict[str, str]:
        text = self.resolver.read_text(f"{TILES}/{stem}.locale={self.lang}.json")
        return loads_lenient(text) if text else {}

    def features(self) -> List[Dict[str, Any]]:
        if self._features is not None:
            return self._features
        xaml = self.resolver.read_text(f"{TILES}/overlay.xaml") or ""
        names = {**self._names("airfields"), **self._names("cities")}
        out = []
        for style, left, top in self._CONTROL.findall(xaml):
            kind = OVERLAY_KINDS.get(style)
            if kind:
                out.append({"kind": kind, "name": "",
                            "x": WORLD_M - float(top) * OVERLAY_M_PER_PX,
                            "z": float(left) * OVERLAY_M_PER_PX})
        # Labels are positioned by their text box, not the marker; attach each
        # to the nearest marker of its family so the name sits on the symbol.
        markers = {"airfield": [f for f in out if f["kind"] == "airfield"],
                   "city": [f for f in out if f["kind"] in ("city", "town")]}
        for key, left, top in self._LABEL.findall(xaml):
            family = "airfield" if key.startswith("af") else "city"
            lx, lz = WORLD_M - float(top) * OVERLAY_M_PER_PX, float(left) * OVERLAY_M_PER_PX
            pool = [f for f in markers[family] if not f["name"]]
            if not pool:
                continue
            nearest = min(pool, key=lambda f: (f["x"] - lx) ** 2 + (f["z"] - lz) ** 2)
            nearest["name"] = names.get(key) or key[2:]
        self._features = out
        return out
