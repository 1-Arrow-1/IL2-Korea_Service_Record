import hashlib
import json
import threading
from dataclasses import replace
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from korea_service_record import updater
from korea_service_record.app import create_app
from career_helper import STRINGS


class _Server:
    def __init__(self, setup=b"signed setup bytes", digest=None):
        self.setup = setup
        self.digest = digest or hashlib.sha256(setup).hexdigest()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def _handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/latest":
                    base = f"http://127.0.0.1:{self.server.server_port}"
                    body = {
                        "tag_name": "v2.2.5",
                        "published_at": "2026-10-09T12:00:00Z",
                        "body": "Release notes",
                        "html_url": base + "/release",
                        "assets": [{
                            "name": "IL2_Korea_Service_Record_Setup_v2.2.5.exe",
                            "browser_download_url": base + "/setup.exe",
                            "size": len(outer.setup),
                            "digest": "sha256:" + outer.digest,
                        }],
                    }
                    payload = json.dumps(body).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                elif self.path == "/setup.exe":
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(outer.setup)))
                    self.end_headers()
                    self.wfile.write(outer.setup)
                else:
                    self.send_error(404)

            def log_message(self, *_args):
                pass

        return Handler

    def __enter__(self):
        self.thread.start()
        return f"http://127.0.0.1:{self.httpd.server_port}"

    def __exit__(self, *_args):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()


def test_version_comparison_is_numeric_and_understands_beta():
    assert updater.is_newer("2.2.5 beta", "2.2.4")
    assert updater.is_newer("2.2.5", "2.2.5 beta")
    assert not updater.is_newer("2.2.4", "2.2.4")
    assert not updater.is_newer("2.2.3", "2.2.4")
    assert updater.version_key("2.10.0") > updater.version_key("2.9.9")


def test_local_release_check_download_digest_and_signer(tmp_path):
    signed = updater.SignatureInfo("Valid", "AA BB CC", "test signer")
    progress = []
    with _Server() as base:
        release = updater.fetch_latest(base + "/latest")
        result = updater.download_and_verify(
            release,
            destination=tmp_path / release.asset.name,
            signature_source=tmp_path / "running.exe",
            signature_reader=lambda _path: signed,
            progress=lambda stage, done, total: progress.append((stage, done, total)),
        )
    assert release.version == "2.2.5"
    assert release.notes == "Release notes"
    assert result.read_bytes() == b"signed setup bytes"
    assert {row[0] for row in progress} == {
        "downloading", "verifying_hash", "verifying_signature"
    }


def test_wrong_github_digest_aborts_before_signature_check(tmp_path):
    called = []
    with _Server(digest="0" * 64) as base:
        release = updater.fetch_latest(base + "/latest")
        with pytest.raises(updater.UpdateError, match="!=") as error:
            updater.download_and_verify(
                release,
                destination=tmp_path / release.asset.name,
                signature_reader=lambda path: called.append(path),
            )
    assert error.value.code == "digest_mismatch"
    assert called == []


def test_download_stops_when_server_exceeds_declared_asset_size(tmp_path):
    called = []
    with _Server(setup=b"larger than declared") as base:
        release = updater.fetch_latest(base + "/latest")
        release = replace(
            release,
            asset=replace(release.asset, size=1),
        )
        with pytest.raises(updater.UpdateError) as error:
            updater.download_and_verify(
                release,
                destination=tmp_path / release.asset.name,
                signature_reader=lambda path: called.append(path),
            )
    assert error.value.code == "size_mismatch"
    assert called == []


def test_different_signer_is_rejected(tmp_path):
    signatures = iter([
        updater.SignatureInfo("Valid", "AAAA"),
        updater.SignatureInfo("Valid", "BBBB"),
    ])
    with _Server() as base:
        release = updater.fetch_latest(base + "/latest")
        with pytest.raises(updater.UpdateError) as error:
            updater.download_and_verify(
                release,
                destination=tmp_path / release.asset.name,
                signature_source=tmp_path / "running.exe",
                signature_reader=lambda _path: next(signatures),
            )
    assert error.value.code == "signer_mismatch"


def test_installer_waits_for_game_and_tracker_then_uses_silent_flags(tmp_path):
    setup = tmp_path / "setup.exe"
    setup.write_bytes(b"fixture")
    launched = []
    updater.launch_installer(
        setup,
        process_check=lambda name: False,
        tracker_stop=lambda: True,
        launcher=lambda args, **kwargs: launched.append((args, kwargs)),
    )
    assert launched[0][0] == [
        str(setup), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"
    ]


def test_installer_refuses_to_run_while_game_is_open(tmp_path):
    with pytest.raises(updater.UpdateError) as error:
        updater.launch_installer(
            tmp_path / "setup.exe",
            process_check=lambda name: name == "IL2Series.exe",
            tracker_stop=lambda: True,
        )
    assert error.value.code == "game_running"



def test_helper_updater_strings_match_in_all_six_languages():
    english = set(STRINGS["en"])
    assert set(STRINGS) == {"en", "de", "es", "fr", "ru", "zh"}
    assert all(set(strings) == english for strings in STRINGS.values())
    assert all("tab_update" in strings for strings in STRINGS.values())


def test_tracker_has_update_shutdown_that_uses_separate_hook():
    app = create_app()
    called = []
    app.config["UPDATE_SHUTDOWN"] = lambda: called.append("update")
    with app.test_client() as client:
        response = client.post("/api/update-shutdown")
    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
    assert called == ["update"]


def test_release_version_and_silent_installer_contract_stay_wired():
    root = Path(__file__).resolve().parent.parent
    build = (root / "tools" / "build_release.ps1").read_text(encoding="utf-8")
    installer = (root / "installer" / "IL2_Korea_Service_Record.iss").read_text(
        encoding="utf-8"
    )
    assert 'korea_service_record\\version.py' in build
    assert "git add -- $iss $zipPy $runtimeVersion" in build
    assert "version.py says" in build
    assert "UsePreviousAppDir=yes" in installer
    assert "UsePreviousSetupType=yes" in installer
    assert "UsePreviousTasks=yes" in installer
    assert 'Parameters: "--from-tracker --after-update"' in installer
    assert "Flags: nowait skipifnotsilent" in installer
    assert "Result := FindIL2Root(GetStoredIL2Path());" in installer


def test_tracker_process_is_allowed_time_to_finish_exiting(tmp_path, monkeypatch):
    setup = tmp_path / "setup.exe"
    setup.write_bytes(b"fixture")
    checks = iter([False, True, True, False])
    launched = []
    monkeypatch.setattr(updater.time, "sleep", lambda _seconds: None)
    updater.launch_installer(
        setup,
        process_check=lambda _name: next(checks),
        tracker_stop=lambda: True,
        launcher=lambda args, **kwargs: launched.append(args),
    )
    assert launched
