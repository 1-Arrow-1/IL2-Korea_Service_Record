"""Exercise updater download and trust checks against a local signed Setup.

Usage:
    python tools/test_updater_flow.py installer/Output/IL2_Korea_Service_Record_Setup_v2.2.4.exe

The supplied signed Setup acts as both the locally served release asset and
the trusted running executable.  Nothing is installed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from korea_service_record import updater


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("setup", type=Path)
    args = parser.parse_args()
    setup = args.setup.resolve()
    match = updater.SETUP_PATTERN.fullmatch(setup.name)
    if not setup.is_file() or not match:
        parser.error("setup must be an IL2_Korea_Service_Record_Setup_v*.exe file")
    version = match.group(1)
    digest = hashlib.sha256(setup.read_bytes()).hexdigest()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            base = f"http://127.0.0.1:{self.server.server_port}"
            if self.path == "/latest":
                body = json.dumps({
                    "tag_name": "v" + version,
                    "published_at": "2026-10-09T00:00:00Z",
                    "body": "Local updater verification",
                    "html_url": base + "/release",
                    "assets": [{
                        "name": setup.name,
                        "browser_download_url": base + "/setup.exe",
                        "size": setup.stat().st_size,
                        "digest": "sha256:" + digest,
                    }],
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/setup.exe":
                self.send_response(200)
                self.send_header("Content-Length", str(setup.stat().st_size))
                self.end_headers()
                with setup.open("rb") as source:
                    while block := source.read(1024 * 1024):
                        self.wfile.write(block)
            else:
                self.send_error(404)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        release = updater.fetch_latest(base + "/latest")
        destination = Path(tempfile.gettempdir()) / ("updater-test-" + setup.name)
        verified = updater.download_and_verify(
            release, signature_source=setup, destination=destination,
            progress=lambda stage, done, total: print(
                f"{stage}: {done}/{total}" if stage == "downloading" else stage
            ),
        )
        if hashlib.sha256(verified.read_bytes()).hexdigest() != digest:
            raise RuntimeError("verified download changed on disk")
        print(f"verified {release.version}: {verified}")
        verified.unlink(missing_ok=True)
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    raise SystemExit(main())
