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
import time
import zlib
from pathlib import Path
from typing import Optional

from flask import Flask, Response, jsonify, request, send_from_directory

from .career.aggregator import CareerAggregator
from .icons import SHEETS
from .gamedata import loads_lenient
from .i18n import (apply_game_strings, available as available_languages,
                   game_code, normalise, ui_strings)
from .photos import PhotoStore
from .settings import Settings
from .assets import default_cache_dir
from .locate import find_game_dir

logger = logging.getLogger(__name__)

def helper_command() -> Optional[list]:
    """How to start the Career Helper here, or None if there is none."""
    import sys
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).parent / "IL2_Korea_Career_Helper.exe"
        return [str(exe)] if exe.is_file() else None
    script = Path(__file__).resolve().parent.parent / "career_helper.py"
    return [sys.executable, str(script)] if script.is_file() else None


def create_app(game_dir: Optional[Path] = None) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")

    # See locate.py: what setup was told beats anything guessed here, and the
    # guessing covers non-Steam installations as well as Steam's own libraries.
    resolved = find_game_dir(Path(game_dir) if game_dir else None)
    app.config["PHOTOS"] = PhotoStore(default_cache_dir().parent / "photos")
    app.config["SETTINGS"] = Settings(default_cache_dir().parent)
    app.config["STARTED_AT"] = time.time()
    app.config["STARTED"] = time.strftime("%Y-%m-%d %H:%M:%S")
    app.config["GAME_DIR"] = resolved
    # One aggregator per language, built on demand and kept. LocaleStrings and
    # WorldObjectIndex each hold a single language's names, and a career with a
    # detail-page override needs a *different* language from the rest of the
    # application at the same time — so these cannot be one mutable instance.
    # Building is cheap after the first time: the world-object index is cached
    # on disk per language.
    app.config["AGGREGATORS"] = {}
    if resolved:
        logger.info("Game directory: %s", resolved)
    else:
        logger.warning("No IL-2 Korea installation found")

    def aggregator_for(language: str) -> CareerAggregator:
        """The aggregator for one language, built on first use."""
        cache = app.config["AGGREGATORS"]
        if language not in cache:
            cache[language] = CareerAggregator(
                resolved, lang=game_code(language),
                corrections_on=lambda: app.config["SETTINGS"].corrected_times)
            logger.info("Built aggregator for %s (game locale %s)", language, game_code(language))
        return cache[language]

    def aggregator(career_id: Optional[str] = None) -> Optional[CareerAggregator]:
        """
        The aggregator for the language this request should render in.

        Pass a career id wherever the answer is that career's own detail page:
        an override there must reach the game's names too, not only the
        tracker's labels, or the medals come back in the wrong language.
        """
        if resolved is None:
            return None
        language = app.config["SETTINGS"].resolve(career_id)
        cache = app.config["AGGREGATORS"]
        if language not in cache:
            cache[language] = CareerAggregator(
                resolved, lang=game_code(language),
                corrections_on=lambda: app.config["SETTINGS"].corrected_times)
            logger.info("Built aggregator for %s (game locale %s)",
                        language, game_code(language))
        return cache[language]

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

    @app.route("/logbook")
    def logbook_page():
        """The flight record on its own page, so it prints as the form."""
        html = (Path(app.static_folder) / "logbook.html").read_text(encoding="utf-8")
        html = html.replace("__ASSET_VERSION__", asset_version())
        return Response(html, mimetype="text/html", headers={"Cache-Control": "no-store"})

    @app.route("/api/icon/<kind>/<ident>")
    def api_icon(kind: str, ident: str):
        """
        Medal, rank or squadron artwork sliced from the game's atlases.

        ?h=<px> asks for a scaled variant. A missing icon is a 404 rather than
        a placeholder, so the page falls back to text on its own.
        """
        agg = aggregator()
        if agg is None or kind not in SHEETS:
            return ("", 404)
        try:
            height = int(request.args.get("h", 0)) or None
        except ValueError:
            height = None
        if height is not None and not (8 <= height <= 512):
            height = None
        data = agg.icons.png(kind, ident, height)
        if data is None:
            return ("", 404)
        return Response(data, mimetype="image/png",
                        headers={"Cache-Control": "public, max-age=31536000"})

    @app.route("/api/helper", methods=["GET", "POST"])
    def api_helper():
        """
        The Career Helper, launched from the page. GET says whether one is
        available (the frozen exe beside this one, or the script in a source
        checkout); POST starts it as its own process - it is a desktop window
        that writes to the career, deliberately separate from this server.
        """
        import subprocess
        cmd = helper_command()
        if request.method == "GET":
            return jsonify({"available": cmd is not None})
        if cmd is None:
            return jsonify({"ok": False, "reason": "no helper"}), 404
        try:
            subprocess.Popen(cmd + ["--from-tracker"], cwd=str(Path(cmd[0]).parent), close_fds=True)
        except OSError as exc:
            logger.warning("Career Helper failed to start: %s", exc)
            return jsonify({"ok": False, "reason": str(exc)}), 500
        return jsonify({"ok": True})

    @app.route("/api/quit", methods=["POST"])
    def api_quit():
        """
        Close the Service Record from the page. Closing the browser tab
        leaves the tray server running, which even the author found
        non-obvious; this does what the tray's Quit does. Only the launcher
        installs the hook, so a bare Flask test app answers 409.
        """
        hook = app.config.get("SHUTDOWN")
        if hook is None:
            return jsonify({"ok": False, "reason": "no shutdown hook"}), 409
        hook()
        return jsonify({"ok": True})

    @app.route("/api/ribbon/<int:award_id>")
    def api_ribbon(award_id: int):
        """A service ribbon with its devices, composed from the mod's own art."""
        agg = aggregator()
        if agg is None:
            return ("", 404)
        data = agg.ribbons.png(award_id)
        if data is None:
            return ("", 404)
        return Response(data, mimetype="image/png",
                        headers={"Cache-Control": "public, max-age=31536000"})

    @app.route("/api/medal/<int:award_id>")
    def api_medal(award_id: int):
        """A full-size medal with its devices on the drape, for the coat."""
        agg = aggregator()
        if agg is None:
            return ("", 404)
        data = agg.medals.png(award_id)
        if data is None:
            return ("", 404)
        return Response(data, mimetype="image/png",
                        headers={"Cache-Control": "public, max-age=31536000"})

    @app.route("/api/photo/<path:career_id>/<int:pilot_id>", methods=["GET"])
    def api_photo(career_id: str, pilot_id: int):
        """
        A pilot's portrait: the user's upload if there is one, otherwise the
        portrait the game itself ships for that pilot. ?avatar= carries the
        pilot's avatarPath so this needs no database lookup of its own.
        """
        data = app.config["PHOTOS"].read(career_id, pilot_id)
        if data is None:
            agg = aggregator()
            avatar = request.args.get("avatar", "")
            if agg is not None and avatar:
                try:
                    height = int(request.args.get("h", 0)) or None
                except ValueError:
                    height = None
                data = agg.icons.image_png(
                    f"nsdata/assets/pilotphotos/{avatar}.dds", height)
        if data is None:
            return ("", 404)
        return Response(data, mimetype="image/png",
                        headers={"Cache-Control": "no-cache"})

    @app.route("/api/photo/<path:career_id>/<int:pilot_id>", methods=["PUT", "DELETE"])
    def api_photo_write(career_id: str, pilot_id: int):
        store = app.config["PHOTOS"]
        if request.method == "DELETE":
            return jsonify({"deleted": store.delete(career_id, pilot_id)})
        error = store.save(career_id, pilot_id, request.get_data())
        if error:
            return jsonify({"error": error}), 400
        return jsonify({"saved": True})

    @app.route("/api/emblem/<kind>/<ident>")
    def api_emblem(kind: str, ident: str):
        """Name, in-game description and full-size art, for the lightbox."""
        agg = aggregator()
        if agg is None:
            return jsonify({"error": "game_not_found"}), 404
        detail = agg.emblem_detail(kind, ident)
        if detail is None:
            return jsonify({"error": "not_found"}), 404
        return jsonify(detail)

    # -- api ---------------------------------------------------------------

    @app.route("/api/settings", methods=["GET", "POST"])
    def api_settings():
        """
        Read or change the user's preferences.

        A language change rebuilds the aggregator, because the game's own
        names — medals, ranks, mission types, what a target is called — come
        from per-language files rather than from anything the front end can
        translate.
        """
        settings = app.config["SETTINGS"]
        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
            if "language" in payload:
                chosen = settings.set_language(payload.get("language", ""))
                logger.info("Global language set to %s (game locale %s)",
                            chosen, game_code(chosen))
            if "corrected_times" in payload:
                settings.set_corrected_times(bool(payload["corrected_times"]))
        return jsonify({
            "language": settings.language,
            "languages": available_languages(),
            "overrides": settings.career_overrides(),
            "corrected_times": settings.corrected_times,
        })

    @app.route("/api/settings/career/<path:career_id>", methods=["GET", "POST"])
    def api_career_settings(career_id: str):
        """
        The detail-page language for one career.

        An empty language clears the override, which is what "Default" means in
        the picker: follow the global setting, including when it later changes.
        """
        settings = app.config["SETTINGS"]
        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
            settings.set_career_language(career_id, payload.get("language") or None)
        return jsonify({
            "career": career_id,
            "language": settings.career_language(career_id) or "",
            "resolved": settings.resolve(career_id),
            "languages": available_languages(),
        })

    @app.route("/locales/<code>.json")
    def api_locale(code: str):
        """
        The tracker's own UI strings for one language.

        Served from a route rather than as a static file so an unknown code
        answers with English instead of a 404 the front end would have to
        special-case.
        """
        bundle = ui_strings(normalise(code))
        # The game already names courage, flight hours and the rest in all six
        # languages, and its wording is what the player sees one screen away.
        agg = app.config["AGGREGATORS"].get(app.config["SETTINGS"].language)             or aggregator()
        if agg is not None:
            apply_game_strings(bundle, normalise(code),
                               agg.resolver.read_text, loads_lenient)
        return jsonify(bundle)

    @app.route("/api/ping")
    def api_ping():
        """Identifies this server to a second launch of the exe.

        Without a console window there is nothing to tell the user the tracker
        is already running, so the second copy asks the port who is on it. Any
        other program that happens to hold 5002 will not answer to this, and
        the launcher reports a port conflict instead of opening a browser onto
        a stranger's web page.
        """
        return jsonify({"app": "korea-service-record"})

    @app.route("/api/careers")
    def api_careers():
        agg = aggregator()
        if agg is None:
            return jsonify({"error": "game_not_found", "careers": []}), 200
        return jsonify({"careers": agg.list_careers()})

    def auto_correct(career_id: str) -> None:
        """A career kept corrected by standing order (set in the Career
        Helper) gets its new missions applied when it is read."""
        agg = aggregator(career_id)
        if agg is None:
            return
        meta = agg._career_files().get(career_id)
        if meta is None:
            return
        try:
            from .corrections import auto_sync
            auto_sync(Path(meta.path), agg.game_dir)
        except Exception:                    # noqa: BLE001 - never break the page over this
            logger.exception("Automatic flight-time correction failed for %s", career_id)

    @app.route("/api/career/<path:career_id>")
    def api_career(career_id: str):
        auto_correct(career_id)
        agg = aggregator(career_id)
        if agg is None:
            return jsonify({"error": "game_not_found"}), 404
        try:
            pilot_id = int(request.args["pilot"]) if "pilot" in request.args else None
        except ValueError:
            pilot_id = None
        detail = agg.career_detail(career_id, pilot_id)
        if detail is None:
            return jsonify({"error": "career_not_found"}), 404
        settings = app.config["SETTINGS"]
        detail["language"] = settings.resolve(career_id)
        detail["language_override"] = settings.career_language(career_id) or ""
        return jsonify(detail)

    @app.route("/api/mission/<path:career_id>/<int:mission_id>")
    def api_mission(career_id: str, mission_id: int):
        """Full debrief for one mission, including every pilot who flew."""
        agg = aggregator(career_id)
        if agg is None:
            return jsonify({"error": "game_not_found"}), 404
        detail = agg.mission_detail(career_id, mission_id)
        if detail is None:
            return jsonify({"error": "mission_not_found"}), 404
        return jsonify(detail)

    @app.route("/api/maptile/<int(signed=True):zoom>/<int:row>/<int:col>")
    def api_maptile(zoom: int, row: int, col: int):
        """One tile of the game's chart, from the player's own installation."""
        agg = aggregator()
        if agg is None:
            return ("", 404)
        data = agg.tiles.tile(zoom, row, col)
        if data is None:
            return ("", 404)
        return Response(data, mimetype="image/jpeg",
                        headers={"Cache-Control": "public, max-age=31536000"})

    @app.route("/api/map/overlay")
    def api_map_overlay():
        """Airfields and towns with their names, for the map's labels."""
        agg = aggregator()
        if agg is None:
            return jsonify({"error": "game_not_found"}), 404
        return jsonify({"features": agg.overlay.features()})

    @app.route("/api/map/<path:career_id>")
    def api_map_career(career_id: str):
        """Every route and victory of the career, for the operations map."""
        agg = aggregator(career_id)
        if agg is None:
            return jsonify({"error": "game_not_found"}), 404
        try:
            pilot_id = int(request.args["pilot"]) if "pilot" in request.args else None
        except ValueError:
            pilot_id = None
        data = agg.career_map(career_id, pilot_id)
        if data is None:
            return jsonify({"error": "career_not_found"}), 404
        return jsonify(data)

    @app.route("/api/citation/<path:career_id>/<int:pilot_id>/<int:award_id>")
    def api_citation(career_id: str, pilot_id: int, award_id: int):
        """The written citation for one of a pilot's decorations."""
        agg = aggregator(career_id)
        if agg is None:
            return jsonify({"error": "game_not_found"}), 404
        earned = request.args.get("earned", "")
        data = agg.citation(career_id, pilot_id, award_id, earned)
        return jsonify(data or {})

    @app.route("/api/logbook/<path:career_id>")
    @app.route("/api/logbook/<path:career_id>/<int:pilot_id>")
    def api_logbook(career_id: str, pilot_id: Optional[int] = None):
        """
        The individual flight record. The form's own language wins over
        the page's - an AF Form 5 is an English document, a Soviet flight
        book a Russian one - so the names of aircraft and missions are read
        in that language; the KPA book has no fixed language here and
        follows the page.
        """
        agg = aggregator(career_id)
        if agg is None:
            return jsonify({"error": "game_not_found"}), 404
        data = agg.logbook(career_id, pilot_id)
        if data is None:
            return jsonify({"error": "pilot_not_found"}), 404
        wanted = {"usaf": "en", "sov": "ru"}.get(data["form"])
        if wanted and wanted != app.config["SETTINGS"].resolve(career_id):
            data = aggregator_for(wanted).logbook(career_id, pilot_id) or data
        return jsonify(data)

    @app.route("/api/track/<path:career_id>/<int:mission_id>")
    def api_track(career_id: str, mission_id: int):
        """The player's flown track for a mission, from the flight log."""
        agg = aggregator(career_id)
        if agg is None:
            return jsonify({"error": "game_not_found"}), 404
        data = agg.mission_track(career_id, mission_id)
        if data is None:
            return jsonify({"error": "mission_not_found"}), 404
        return jsonify(data)

    @app.route("/api/pilot/<path:career_id>/<int:pilot_id>")
    def api_pilot(career_id: str, pilot_id: int):
        """Compact summary for the roster modal."""
        agg = aggregator(career_id)
        if agg is None:
            return jsonify({"error": "game_not_found"}), 404
        summary = agg.pilot_summary(career_id, pilot_id)
        if summary is None:
            return jsonify({"error": "pilot_not_found"}), 404
        return jsonify(summary)

    @app.route("/api/debug")
    def api_debug():
        agg = aggregator()
        game_dir = app.config.get("GAME_DIR")
        info = {
            "game_dir": str(game_dir) if game_dir else None,
            "started": app.config.get("STARTED"),
            "uptime_s": round(time.time() - app.config.get("STARTED_AT", time.time())),
            "locale_sources": agg.locale.sources() if agg else None,
            "award_definitions": len(agg.awards_cfg.definitions) if agg else 0,
            "rank_strings": len(agg.locale.ranks) if agg else 0,
            "icons": {k: len(agg.icons.sheet(k).crops) for k in SHEETS} if agg else {},
            "world_objects": len(agg.objects.objects) if agg else 0,
            "award_strings": len(agg.locale.awards) if agg else 0,
        }
        return jsonify(info)

    return app
