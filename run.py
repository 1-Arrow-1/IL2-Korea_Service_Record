"""
Launch the Korea Service Record.

    python run.py
    python run.py --game "E:/SteamLibrary/steamapps/common/IL2Series"
    python run.py --port 5002 --no-browser

The game folder is auto-detected across the usual Steam drives, or taken from
KOREA_GAME_DIR, so the packaged exe can be double-clicked with no setup.
"""

import argparse
import logging
import threading
import webbrowser
from pathlib import Path

from korea_service_record.app import create_app

DEFAULT_PORT = 5002


def main() -> int:
    parser = argparse.ArgumentParser(description="IL-2 Korea Service Record")
    parser.add_argument("--game", help="path to the IL-2 Korea installation")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s")

    app = create_app(Path(args.game) if args.game else None)
    url = f"http://{args.host}:{args.port}/"

    if app.config.get("GAME_DIR") is None:
        print("No IL-2 Korea installation found. Pass --game or set KOREA_GAME_DIR.")
    else:
        print(f"Reading: {app.config['GAME_DIR']}")
    print(f"Serving: {url}")

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
