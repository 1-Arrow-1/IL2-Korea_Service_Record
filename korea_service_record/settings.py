"""
User preferences, kept outside the game installation.

The tracker is read-only towards IL-2 — that is the promise printed at the
foot of every page — so its own settings go where the pilot portraits already
go, under ``%LOCALAPPDATA%/IL2KoreaTracker``. A Steam verify or a game patch
then cannot take the user's settings with it, and the game folder stays
untouched. It is also why a per-career language override is stored here,
keyed by career, rather than written into the career database.

Language works on two levels, following the Great Battles tracker:

* a **global** language, chosen at installation, covering every screen;
* a **per-career override** for the detail page only, defaulting to "follow
  the global setting".

The override exists for authenticity rather than convenience: a German player
flying a USAF career can read that man's record — his medals, his rank, his
mission types — in English, while the rest of the application stays German.
Which means the override has to reach the *game's* locale files too, not just
the tracker's own labels; see ``CareerAggregator``, one per language.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .i18n import DEFAULT, normalise

logger = logging.getLogger(__name__)

FILENAME = "settings.json"

# Written by the installer next to the executable so the very first run already
# speaks the language the user chose during setup, before any settings file
# exists. Mirrors the Great Battles tracker's locale_setting.txt.
INSTALL_LOCALE_FILE = "locale_setting.txt"
LOCALE_ENV_VAR = "IL2K_TRACKER_LOCALE"

# Career ids are pilot name plus squadron and arrive over HTTP, so they are
# never used as a path — but they are used as a JSON key, and this keeps the
# file legible and bounded.
_SAFE_KEY = re.compile(r"[^\w ,.'\-]", re.UNICODE)


class Settings:
    """Read/write access to the handful of things the user can choose."""

    def __init__(self, root: Path, install_dir: Optional[Path] = None):
        self.path = Path(root) / FILENAME
        self.install_dir = Path(install_dir) if install_dir else Path.cwd()

    # -- storage -----------------------------------------------------------

    def _read(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            # A corrupt settings file must not stop the tracker opening; the
            # defaults are perfectly usable.
            logger.warning("Ignoring unreadable settings %s: %s", self.path, exc)
            return {}

    def _write(self, data: Dict[str, Any]) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
            return True
        except OSError as exc:
            logger.error("Cannot save settings %s: %s", self.path, exc)
            return False

    @staticmethod
    def _key(career_id: str) -> str:
        return _SAFE_KEY.sub("_", str(career_id or "")).strip()[:160]

    # -- global language ---------------------------------------------------

    def _installed_language(self) -> Optional[str]:
        """What setup chose, for a first run with no settings file yet."""
        env = os.environ.get(LOCALE_ENV_VAR)
        if env:
            return env
        try:
            text = (self.install_dir / INSTALL_LOCALE_FILE).read_text(
                encoding="utf-8").strip()
            return text or None
        except (OSError, ValueError):
            return None

    @property
    def language(self) -> str:
        stored = self._read().get("language")
        if stored:
            return normalise(stored)
        installed = self._installed_language()
        return normalise(installed) if installed else DEFAULT

    def set_language(self, code: str) -> str:
        """Store the global language and return what was actually stored."""
        chosen = normalise(code)
        data = self._read()
        data["language"] = chosen
        self._write(data)
        return chosen

    # -- per-career detail page override -----------------------------------

    def career_language(self, career_id: str) -> Optional[str]:
        """The override for one career, or None for "follow the global"."""
        careers = self._read().get("careers")
        if not isinstance(careers, dict):
            return None
        entry = careers.get(self._key(career_id))
        if not isinstance(entry, dict):
            return None
        stored = entry.get("language")
        return normalise(stored) if stored else None

    def set_career_language(self, career_id: str,
                            code: Optional[str]) -> Optional[str]:
        """
        Set or clear one career's override.

        An empty code clears it rather than storing a language, which is what
        "Default" in the picker means — follow the global setting from now on,
        including when the global setting later changes.
        """
        data = self._read()
        careers = data.setdefault("careers", {})
        if not isinstance(careers, dict):
            careers = data["careers"] = {}
        key = self._key(career_id)
        if not code:
            careers.pop(key, None)
            self._write(data)
            return None
        chosen = normalise(code)
        careers[key] = {"language": chosen}
        self._write(data)
        return chosen

    def resolve(self, career_id: Optional[str] = None) -> str:
        """The language one page should actually be rendered in."""
        if career_id:
            override = self.career_language(career_id)
            if override:
                return override
        return self.language

    def career_overrides(self) -> List[Dict[str, str]]:
        """Every stored override, for a settings screen to list."""
        careers = self._read().get("careers")
        if not isinstance(careers, dict):
            return []
        return [{"career": key, "language": value.get("language", "")}
                for key, value in careers.items() if isinstance(value, dict)]
