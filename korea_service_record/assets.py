"""
Asset resolution: loose file first, archive second, cached on disk.

The game itself lets a loose file under ``<game>/data`` shadow the copy inside
a ``.gtp``, and mods rely on that. This resolver follows the same rule, so a
modded install shows the modded names and artwork while a stock install still
works — which is the whole point, since ``ranks.locale`` and the medal atlases
are sealed inside the encrypted ``Interface.gtp``.

Lookup order for a virtual path such as ``nsdata/assets/locale/ranks.locale=eng.json``:

1. ``<game>/data/<vpath>``            — loose file, i.e. stock-extracted or modded
2. ``<cache>/<vpath>``                — extracted by us on an earlier run
3. the archives                       — extracted now, then written to the cache

Nothing is ever written into the game folder. The cache lives under the user's
local app data (or ``KOREA_TRACKER_CACHE``), so the install stays untouched and
uninstalling the tracker leaves no trace in it.
"""

import logging
import os
from pathlib import Path
from typing import Iterable, List, Optional

from .gtp.archive import GtpArchive, find_archives

logger = logging.getLogger(__name__)

# Archives worth searching, most likely first. Interface.gtp holds the UI
# assets: locale strings, the award atlases and awards.xaml.
PREFERRED_ARCHIVES = ("Interface.gtp", "Missions.gtp")


def default_cache_dir() -> Path:
    override = os.environ.get("KOREA_TRACKER_CACHE")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache")
    return Path(base) / "IL2KoreaTracker" / "assets"


class AssetResolver:
    """Finds game assets by virtual path, extracting on demand."""

    def __init__(self, game_dir: Path, cache_dir: Optional[Path] = None):
        self.game_dir = Path(game_dir)
        self.cache_dir = Path(cache_dir) if cache_dir else default_cache_dir()
        self._archives: Optional[List[Path]] = None

    # -- locations ---------------------------------------------------------

    def _loose_path(self, vpath: str) -> Path:
        return self.game_dir / "data" / vpath.lstrip("/")

    def _cache_path(self, vpath: str) -> Path:
        return self.cache_dir / vpath.lstrip("/")

    def _archive_paths(self) -> List[Path]:
        if self._archives is None:
            found = find_archives(self.game_dir)
            order = {name.lower(): i for i, name in enumerate(PREFERRED_ARCHIVES)}
            self._archives = sorted(
                found, key=lambda p: (order.get(p.name.lower(), len(order)), p.name))
        return self._archives

    # -- resolution --------------------------------------------------------

    def source_of(self, vpath: str) -> str:
        """Where a path would come from, without extracting: loose/cache/archive/missing."""
        if self._loose_path(vpath).is_file():
            return "loose"
        if self._cache_path(vpath).is_file():
            return "cache"
        return "archive" if self._archive_paths() else "missing"

    def read(self, vpath: str, use_cache: bool = True) -> Optional[bytes]:
        """
        Return the bytes for a virtual path, or None if it cannot be found.

        A loose file always wins, so a mod's edits are what the user sees —
        matching the engine's own behaviour.
        """
        loose = self._loose_path(vpath)
        if loose.is_file():
            try:
                return loose.read_bytes()
            except OSError as exc:
                logger.warning("Cannot read loose asset %s: %s", loose, exc)

        cached = self._cache_path(vpath)
        if use_cache and cached.is_file():
            try:
                return cached.read_bytes()
            except OSError as exc:
                logger.warning("Cannot read cached asset %s: %s", cached, exc)

        data = self._extract(vpath)
        if data is not None and use_cache:
            self._write_cache(cached, data)
        return data

    def _extract(self, vpath: str) -> Optional[bytes]:
        for archive_path in self._archive_paths():
            try:
                with GtpArchive(archive_path) as archive:
                    data = archive.extract(vpath)
            except (OSError, ValueError) as exc:
                logger.warning("Cannot read %s: %s", archive_path.name, exc)
                continue
            if data is not None:
                logger.info("Extracted %s from %s (%d bytes)",
                            vpath, archive_path.name, len(data))
                return data
        logger.info("Asset not present in any archive: %s", vpath)
        return None

    def _write_cache(self, target: Path, data: bytes) -> None:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Write via a temp file so a crash cannot leave a half-written asset
            # that would then be trusted on the next run.
            tmp = target.with_suffix(target.suffix + ".part")
            tmp.write_bytes(data)
            os.replace(tmp, target)
        except OSError as exc:
            logger.warning("Cannot cache asset %s: %s", target, exc)

    def read_text(self, vpath: str, encoding: str = "utf-8-sig") -> Optional[str]:
        data = self.read(vpath)
        if data is None:
            return None
        return data.decode(encoding, errors="replace")

    def prefetch(self, vpaths: Iterable[str]) -> dict:
        """
        Warm the cache for several paths in one pass over each archive.

        Opening ``Interface.gtp`` once for five files beats five FAT walks —
        the FAT alone is ~9000 entries.
        """
        wanted = {v.lower().lstrip("/"): v for v in vpaths}
        result = {}
        for vpath in list(wanted.values()):
            if self._loose_path(vpath).is_file() or self._cache_path(vpath).is_file():
                result[vpath] = self.source_of(vpath)
                wanted.pop(vpath.lower().lstrip("/"), None)
        if not wanted:
            return result

        for archive_path in self._archive_paths():
            if not wanted:
                break
            try:
                with GtpArchive(archive_path) as archive:
                    for entry in archive.entries():
                        key = entry.vpath.lower().lstrip("/")
                        if key not in wanted:
                            continue
                        vpath = wanted.pop(key)
                        self._write_cache(self._cache_path(vpath), archive.read(entry))
                        result[vpath] = f"extracted:{archive_path.name}"
                        if not wanted:
                            break
            except (OSError, ValueError) as exc:
                logger.warning("Cannot scan %s: %s", archive_path.name, exc)
        for vpath in wanted.values():
            result[vpath] = "missing"
        return result
