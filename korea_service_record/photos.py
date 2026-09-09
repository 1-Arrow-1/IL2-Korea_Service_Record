"""
Pilot photographs supplied by the user.

The game gives every pilot a portrait, but they are generic and there is no way
to put a face of your own on a career. Photos live entirely outside the game
install — under ``%LOCALAPPDATA%/IL2KoreaTracker/photos`` — so nothing here can
touch a game file, and uninstalling the tracker leaves the install as it was.

The crop happens in the browser: the page sends an already-square PNG and this
module only validates and stores it. That keeps the server side small and means
the bytes on disk are exactly what the user saw when they pressed save.
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAX_BYTES = 4 * 1024 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Career ids come from a filename and pilot ids from the database, but both
# arrive over HTTP, so neither is trusted to build a path.
_SAFE = re.compile(r"[^A-Za-z0-9 ,._-]")


class PhotoStore:
    """Reads and writes user-supplied pilot portraits."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _slug(self, career_id: str) -> str:
        return _SAFE.sub("_", career_id).strip()[:120] or "career"

    def path(self, career_id: str, pilot_id: int) -> Path:
        return self.root / self._slug(career_id) / f"{int(pilot_id)}.png"

    def read(self, career_id: str, pilot_id: int) -> Optional[bytes]:
        try:
            target = self.path(career_id, pilot_id)
        except (TypeError, ValueError):
            return None
        if not target.is_file():
            return None
        try:
            return target.read_bytes()
        except OSError as exc:
            logger.warning("Cannot read photo %s: %s", target, exc)
            return None

    def save(self, career_id: str, pilot_id: int, data: bytes) -> Optional[str]:
        """
        Store a portrait. Returns an error string, or None on success.

        Only PNG is accepted, checked by magic number rather than by trusting
        the content type the browser claims.
        """
        if not data:
            return "empty upload"
        if len(data) > MAX_BYTES:
            return f"image larger than {MAX_BYTES // (1024 * 1024)} MB"
        if not data.startswith(PNG_MAGIC):
            return "not a PNG image"
        try:
            target = self.path(career_id, pilot_id)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(target)
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("Cannot save photo: %s", exc)
            return "could not write the file"
        logger.info("Saved portrait for pilot %s (%d bytes)", pilot_id, len(data))
        return None

    def delete(self, career_id: str, pilot_id: int) -> bool:
        try:
            target = self.path(career_id, pilot_id)
        except (TypeError, ValueError):
            return False
        try:
            if target.is_file():
                target.unlink()
                return True
        except OSError as exc:
            logger.warning("Cannot delete photo %s: %s", target, exc)
        return False

    def has(self, career_id: str, pilot_id: int) -> bool:
        try:
            return self.path(career_id, pilot_id).is_file()
        except (TypeError, ValueError):
            return False
