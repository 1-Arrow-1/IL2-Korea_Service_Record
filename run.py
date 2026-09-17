"""
Launch the Korea Service Record.

    python run.py
    python run.py --game "E:/SteamLibrary/steamapps/common/IL2Series"
    python run.py --port 5002 --no-browser
    python run.py --console            # log to the terminal, no tray icon

The game folder is auto-detected across the usual Steam drives, or taken from
KOREA_GAME_DIR, so the packaged exe can be double-clicked with no setup.

The packaged build has no console window, which costs three things the console
was quietly providing. Each is replaced here rather than dropped:

  * **Somewhere to see it running, and a way to stop it.** A tray icon, with
    Open and Quit. Without one the server would be a ghost process stoppable
    only from Task Manager.
  * **Somewhere for errors to go.** Everything is logged to a file beside the
    user's settings, so a bug report still arrives with a traceback.
  * **Notice that it is already running.** Double-clicking a windowless app
    twice is easy and looks like nothing happened, so the second copy asks the
    port who is on it and, if it is us, just opens the browser and exits.

Run under Python with no arguments and it behaves the same way. ``--console``
restores the old behaviour for development.
"""

import argparse
import json
import logging
import os
import socket
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from korea_service_record.app import create_app

DEFAULT_PORT = 5002
LOG_NAME = "tracker.log"

log = logging.getLogger("korea")


def frozen() -> bool:
    return getattr(sys, "frozen", False)


def log_dir() -> Path:
    """Beside the settings and the photographs, never in the game folder."""
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "IL2KoreaTracker" if base else Path.home()


def setup_logging(to_console: bool, debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handlers: list[logging.Handler] = []
    if to_console:
        handlers.append(logging.StreamHandler())
    else:
        try:
            folder = log_dir()
            folder.mkdir(parents=True, exist_ok=True)
            # Truncated per run: this is for "it broke just now, send me the
            # file", not an audit trail, and it must not grow without bound.
            handlers.append(logging.FileHandler(
                folder / LOG_NAME, mode="w", encoding="utf-8"))
        except OSError:
            pass
    logging.basicConfig(level=level, handlers=handlers, force=True,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if not to_console:
        # A windowed build has no stdout, and any stray print() would raise on
        # a None stream. Send the last word of a crash to the log as well.
        def hook(kind, value, tb):
            log.critical("unhandled", exc_info=(kind, value, tb))
        sys.excepthook = hook


def already_running(url: str) -> bool:
    """True when our own server is the one holding the port."""
    try:
        with urllib.request.urlopen(url + "api/ping", timeout=2.0) as response:
            return json.load(response).get("app") == "korea-service-record"
    except (urllib.error.URLError, OSError, ValueError):
        return False


def port_is_free(host: str, port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex((host, port)) != 0


TRAY: dict = {}


def request_quit(shutdown) -> None:
    """
    Shut down from a web request. The response must leave first, so the
    work happens on a timer; the tray's Quit path is used when there is one,
    and os._exit is the backstop for the console mode, where app.run() owns
    the thread and has no shutdown() to call.
    """
    def later():
        try:
            stop = TRAY.get("stop")
            if stop is not None:
                stop()
            elif shutdown is not None:
                shutdown()
        finally:
            threading.Timer(1.5, lambda: os._exit(0)).start()
    threading.Timer(0.4, later).start()


def run_tray(url: str, shutdown) -> bool:
    """Sit in the notification area until the user picks Quit.

    Returns False if a tray icon could not be created, so the caller can fall
    back to simply serving — a tracker with an awkward exit beats one that
    refuses to start.
    """
    try:
        import pystray
        from PIL import Image
    except ImportError:
        return False

    name = "IL2_Korea_Service_Record.ico"
    art = (Path(sys._MEIPASS) / name if frozen()
           else Path(__file__).resolve().parent / "installer" / name)
    try:
        image = Image.open(art)
    except OSError:
        log.warning("tray icon art missing at %s", art)
        return False

    icon = None

    def quit_now(*_):
        shutdown()
        if icon is not None:
            icon.stop()

    # The page's own Close control ends up here too, so the tray icon goes
    # away with the server instead of lingering as a dead entry.
    TRAY["stop"] = quit_now

    menu = pystray.Menu(
        pystray.MenuItem("Open Service Record",
                         lambda *_: webbrowser.open(url), default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_now),
    )
    try:
        icon = pystray.Icon("korea_service_record", image,
                            "IL-2 Korea Service Record", menu)
        icon.run()
    except Exception:                       # noqa: BLE001 - never block startup
        log.exception("tray icon failed")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="IL-2 Korea Service Record")
    parser.add_argument("--game", help="path to the IL-2 Korea installation")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--console", action="store_true",
                        help="log to the terminal and skip the tray icon")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    console = args.console or args.debug or not frozen()
    setup_logging(console, args.debug)
    url = f"http://{args.host}:{args.port}/"

    if not port_is_free(args.host, args.port):
        if already_running(url):
            log.info("already running; opening the browser instead")
            webbrowser.open(url)
            return 0
        log.error("port %d is in use by something else; pass --port",
                  args.port)
        return 1

    app = create_app(Path(args.game) if args.game else None)
    if app.config.get("GAME_DIR") is None:
        log.warning("No IL-2 Korea installation found. "
                    "Pass --game or set KOREA_GAME_DIR.")
    else:
        log.info("Reading: %s", app.config["GAME_DIR"])
    log.info("Serving: %s", url)

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    if console:
        app.config["SHUTDOWN"] = lambda: request_quit(None)
        app.run(host=args.host, port=args.port,
                debug=args.debug, use_reloader=False)
        return 0

    # Windowed: Flask serves on a background thread so the tray icon can own
    # the main one, which is where Windows requires its message loop to live.
    from werkzeug.serving import make_server
    server = make_server(args.host, args.port, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    app.config["SHUTDOWN"] = lambda: request_quit(server.shutdown)

    if not run_tray(url, server.shutdown):
        log.warning("no tray icon; serving until the process is stopped")
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
