"""
Medal, rank and squadron artwork, sliced out of the game's own atlases.

The game keeps its UI art as texture atlases with a Noesis resource dictionary
describing where each image sits::

    awards.xaml     3 atlases,  98 entries   award601021, award601039, ...
    ranks.xaml      6 atlases,  36 entries   rank6011, rank5013, ...
    squadrons.xaml 10 atlases,  73 entries   601039, 501016, ...

Each file declares its own atlas-to-DDS mapping, so nothing here is hard-coded:

    <BitmapImage x:Key="AtlasBitmap.Ranks601" UriSource="Ranks601.dds"/>
    <CroppedBitmap x:Key="rank6011" SourceRect="473,4,461,207"
                   Source="{StaticResource AtlasBitmap.Ranks601}"/>

Atlases are BC7 (DX10) and decode through Pillow. A sliced PNG is cached on
disk, so the cost is paid once per icon and never again — and because the
asset layer prefers loose files, a modded install yields the modded medals.
"""

import hashlib
import io
import logging
import re
from pathlib import Path
from typing import Dict, NamedTuple, Optional, Tuple

logger = logging.getLogger(__name__)

IMAGE_ROOT = "nsdata/assets/images"

# Sheets to read, and the key prefix each uses. Squadron keys are bare ids.
SHEETS = {
    "award": ("awards.xaml", "award"),
    "rank": ("ranks.xaml", "rank"),
    "squadron": ("squadrons.xaml", ""),
}

_ATLAS_RE = re.compile(
    r'x:Key="(AtlasBitmap\.[\w]+)"[^/>]*?UriSource="([^"]+)"', re.S)
_CROP_RE = re.compile(
    r'x:Key="([\w.]+)"[^>]*?SourceRect="([^"]+)"'
    r'[^>]*?Source="\{StaticResource ([^}]+)\}"', re.S)


class Crop(NamedTuple):
    key: str
    atlas: str          # dds filename, e.g. "Ranks601.dds"
    box: Tuple[int, int, int, int]      # left, upper, right, lower


class IconSheet:
    """One xaml resource dictionary and the atlases it references."""

    def __init__(self, resolver, xaml_name: str):
        self.resolver = resolver
        self.xaml_name = xaml_name
        self.crops: Dict[str, Crop] = {}
        self._load()

    def _load(self) -> None:
        text = self.resolver.read_text(f"{IMAGE_ROOT}/{self.xaml_name}")
        if not text:
            logger.warning("Icon sheet missing: %s", self.xaml_name)
            return
        atlases = {k: v for k, v in _ATLAS_RE.findall(text)}
        for key, rect, resource in _CROP_RE.findall(text):
            atlas = atlases.get(resource)
            if atlas is None:
                continue
            try:
                x, y, w, h = (int(n) for n in rect.split(","))
            except ValueError:
                logger.warning("Bad SourceRect for %s: %r", key, rect)
                continue
            self.crops[key] = Crop(key, atlas, (x, y, x + w, y + h))
        logger.info("%s: %d crops across %d atlases",
                    self.xaml_name, len(self.crops), len(atlases))


class IconLibrary:
    """Slices icons on demand and caches the PNGs."""

    def __init__(self, resolver):
        self.resolver = resolver
        self._sheets: Dict[str, IconSheet] = {}
        self._atlas_cache: Dict[str, object] = {}

    def sheet(self, kind: str) -> Optional[IconSheet]:
        if kind not in SHEETS:
            return None
        if kind not in self._sheets:
            self._sheets[kind] = IconSheet(self.resolver, SHEETS[kind][0])
        return self._sheets[kind]

    def _key(self, kind: str, ident: str) -> str:
        # Preserve repeat-citation IDs in the record, but use the plain ROK
        # emblem even with an older mod or previously cached cluster icons.
        if kind == "award" and str(ident) in ("601047", "601048", "601049"):
            ident = "601043"
        return f"{SHEETS[kind][1]}{ident}"

    def _cache_path(self, kind: str, key: str, height: Optional[int], crop) -> Path:
        """
        The cached slice, named after what it was cut from as well as what it
        is: a short hash of the atlas file's fingerprint and the crop
        rectangle. New art, a re-pointed rectangle or a game update all
        change the name, so the cache can never serve yesterday's medal -
        which it did, silently, for every user who upgraded while the
        name was just <key>@<height>.png.
        """
        suffix = f"@{height}" if height else ""
        stamp = hashlib.sha1(
            f"{self.resolver.fingerprint(f'{IMAGE_ROOT}/{crop.atlas}')}|{crop.box}".encode()
        ).hexdigest()[:8]
        return self.resolver.cache_dir / "icons" / kind / f"{key}{suffix}.{stamp}.png"

    def _atlas(self, name: str):
        """Decode one atlas, keeping it in memory for the rest of the run."""
        if name in self._atlas_cache:
            return self._atlas_cache[name]
        data = self.resolver.read(f"{IMAGE_ROOT}/{name}")
        if data is None:
            logger.warning("Atlas not found: %s", name)
            self._atlas_cache[name] = None
            return None
        try:
            from PIL import Image
            image = Image.open(io.BytesIO(data)).convert("RGBA")
        except Exception as exc:                    # noqa: BLE001 - Pillow raises broadly
            logger.warning("Cannot decode atlas %s: %s", name, exc)
            image = None
        self._atlas_cache[name] = image
        return image

    def png(self, kind: str, ident: str,
            height: Optional[int] = None) -> Optional[bytes]:
        """
        Return one icon as PNG bytes, slicing and caching it on first request.

        ``height`` scales the tile down, preserving aspect. Worth doing: a rank
        insignia is 467x198 in the atlas and 200 KB as full-size RGBA, but the
        page shows it 24 pixels tall. Each size is cached separately.

        Returns None when the key is unknown or the atlas cannot be decoded, so
        the caller can fall back to text rather than a broken image.
        """
        sheet = self.sheet(kind)
        if sheet is None:
            return None
        key = self._key(kind, ident)
        crop = sheet.crops.get(key)
        if crop is None:
            return None

        cached = self._cache_path(kind, key, height, crop)
        if cached.is_file():
            try:
                return cached.read_bytes()
            except OSError:
                pass

        atlas = self._atlas(crop.atlas)
        if atlas is None:
            return None
        try:
            tile = atlas.crop(crop.box)
            if height and tile.height > height:
                from PIL import Image
                width = max(1, round(tile.width * height / tile.height))
                tile = tile.resize((width, height), Image.LANCZOS)
        except Exception as exc:                    # noqa: BLE001
            logger.warning("Cannot crop %s from %s: %s", key, crop.atlas, exc)
            return None

        buffer = io.BytesIO()
        tile.save(buffer, format="PNG", optimize=True)
        data = buffer.getvalue()
        try:
            cached.parent.mkdir(parents=True, exist_ok=True)
            tmp = cached.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(cached)
            # Sweep this icon's earlier slices - other stamps, and the
            # unstamped name older versions wrote - so the folder does not
            # grow one orphan per art change.
            stem = f"{key}@{height}" if height else key
            for old in cached.parent.glob(f"{stem}.*png"):
                if old != cached and (old.name == f"{stem}.png" or old.stem.rsplit(".", 1)[0] == stem):
                    try:
                        old.unlink()
                    except OSError:
                        pass
        except OSError as exc:
            logger.warning("Cannot cache icon %s: %s", cached, exc)
        return data

    def image_png(self, vpath: str, height: Optional[int] = None) -> Optional[bytes]:
        """
        Any single image asset as PNG — used for the game's pilot portraits,
        which are individual 512x512 DDS files rather than atlas crops.
        """
        cache = (self.resolver.cache_dir / "images" /
                 (vpath.replace("/", "_") + (f"@{height}" if height else "") + ".png"))
        if cache.is_file():
            try:
                return cache.read_bytes()
            except OSError:
                pass
        data = self.resolver.read(vpath)
        if data is None:
            return None
        try:
            from PIL import Image
            image = Image.open(io.BytesIO(data)).convert("RGBA")
            if height and image.height > height:
                width = max(1, round(image.width * height / image.height))
                image = image.resize((width, height), Image.LANCZOS)
        except Exception as exc:                    # noqa: BLE001
            logger.warning("Cannot decode image %s: %s", vpath, exc)
            return None
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        out = buffer.getvalue()
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache.with_suffix(".part")
            tmp.write_bytes(out)
            tmp.replace(cache)
        except OSError:
            pass
        return out

    def has(self, kind: str, ident: str) -> bool:
        sheet = self.sheet(kind)
        return bool(sheet and self._key(kind, ident) in sheet.crops)
