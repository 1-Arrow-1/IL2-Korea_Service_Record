"""
Flask application factory for the Korea Service Record.

Single page, two views — a career list and a career detail — served from
``static/``, with a small JSON API behind it. Mirrors the Great Battles
tracker's shape so the two feel like one product.

The game directory comes from ``KOREA_GAME_DIR`` or is auto-detected across the
usual Steam library drives, so the exe can be double-clicked with no setup.
"""

import logging
import os
import zlib
from pathlib import Path
from typing import Optional

from flask import Flask, Response, jsonify, send_from_directory

from .career.aggregator import CareerAggregator
from .gamedata import resolve_game_dir

logger = logging.getLogger(__name__)

STEAM_SUFFIX = Path("SteamLibrary/steamapps/common/IL2Series")


def autodetect_game_dir() -> Optional[Path]:
    """Look for an IL-2 Korea install on the usual drives."""
    env = os.environ.get("KOREA_GAME_DIR")
    if env:
        found = resolve_game_dir(Path(env))
        if found:
            return found
        logger.warning("KOREA_GAME_DIR set but not an IL-2 install: %s", env)
    for drive in "CDEFGH":
        candidate = Path(f"{drive}:/") / STEAM_SUFFIX
        if (candidate / "data" / "Career").is_dir():
            return candidate
    return None


def create_app(game_dir: Optional[Path] = None) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")

    resolved = resolve_game_dir(Path(game_dir)) if game_dir else autodetect_game_dir()
    app.config["GAME_DIR"] = resolved
    app.config["AGGREGATOR"] = CareerAggregator(resolved) if resolved else None
    if resolved:
        logger.info("Game directory: %s", resolved)
    else:
        logger.warning("No IL-2 Korea installation found")

    def aggregator() -> Optional[CareerAggregator]:
        return app.config.get("AGGREGATOR")

    # -- views -------------------------------------------------------------

    def asset_version() -> str:
        """
        Cache-buster derived from the static files themselves.

        A hand-maintained "?v=1" is the classic way to ship a UI change that
        half the users never see: the browser keeps the old script and it then
        fails against the new API shape. Deriving the token from mtimes means
        the query string changes whenever a file does, and never otherwise.
        """
        static = Path(app.static_folder)
        stamps = sorted(f"{p.name}:{int(p.stat().st_mtime)}"
                        for p in static.rglob("*")
                        if p.is_file() and p.suffix in (".js", ".css"))
        # crc32 rather than hash(): PYTHONHASHSEED randomises str hashing, which
        # would change the token on every restart and defeat caching entirely.
        return format(zlib.crc32("|".join(stamps).encode()), "08x")

    @app.route("/")
    def index():
        html = (Path(app.static_folder) / "index.html").read_text(encoding="utf-8")
        html = html.replace("__ASSET_VERSION__", asset_version())
        # index.html itself must never be cached, or it would keep pointing at
        # the previous version token and defeat the whole mechanism.
        return Response(html, mimetype="text/html",
                        headers={"Cache-Control": "no-store"})

    # -- api ---------------------------------------------------------------

    @app.route("/api/careers")
    def api_careers():
        agg = aggregator()
        if agg is None:
            return jsonify({"error": "game_not_found", "careers": []}), 200
        return jsonify({"careers": agg.list_careers()})

    @app.route("/api/career/<path:career_id>")
    def api_career(career_id: str):
        agg = aggregator()
        if agg is None:
            return jsonify({"error": "game_not_found"}), 404
        detail = agg.career_detail(career_id)
        if detail is None:
            return jsonify({"error": "career_not_found"}), 404
        return jsonify(detail)

    @app.route("/api/debug")
    def api_debug():
        agg = aggregator()
        game_dir = app.config.get("GAME_DIR")
        info = {
            "game_dir": str(game_dir) if game_dir else None,
            "locale_sources": agg.locale.sources() if agg else None,
            "award_definitions": len(agg.awards_cfg.definitions) if agg else 0,
            "rank_strings": len(agg.locale.ranks) if agg else 0,
            "award_strings": len(agg.locale.awards) if agg else 0,
        }
        return jsonify(info)

    return app
