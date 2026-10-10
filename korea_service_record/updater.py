"""Secure, on-demand updates for the IL-2 Korea Service Record.

The Career Helper owns the UI.  This module keeps network, version,
Authenticode and process handling independent from Tk so the complete check
and download path can be exercised against a local test server.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .version import VERSION


LATEST_RELEASE_API = (
    "https://api.github.com/repos/1-Arrow-1/"
    "IL2-Korea_Service_Record/releases/latest"
)
USER_AGENT = f"IL2-Korea-Service-Record/{VERSION}"
SETUP_PATTERN = re.compile(
    r"^IL2_Korea_Service_Record_Setup_v(.+)\.exe$", re.IGNORECASE
)
VERSION_PATTERN = re.compile(
    r"^v?(\d+)\.(\d+)\.(\d+)(?:[\s._-]*(.*?))?$", re.IGNORECASE
)


class UpdateError(RuntimeError):
    """An updater failure with a stable code for translated UI text."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    size: int
    digest: str


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    published_at: str
    notes: str
    html_url: str
    asset: ReleaseAsset


@dataclass(frozen=True)
class SignatureInfo:
    status: str
    thumbprint: str
    subject: str = ""
    profile_eku: str = ""


ARTIFACT_SIGNING_EKU_PREFIX = "1.3.6.1.4.1.311.97."
ARTIFACT_SIGNING_PUBLIC_TRUST_EKU = "1.3.6.1.4.1.311.97.1.0"


def version_key(value: str) -> tuple[int, int, int, int]:
    """Comparable release key; a final release follows its same-number beta."""
    match = VERSION_PATTERN.fullmatch(str(value).strip())
    if not match:
        raise ValueError(f"invalid version: {value}")
    suffix = (match.group(4) or "").strip().lower()
    final = 0 if suffix else 1
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)), final)


def is_newer(candidate: str, installed: str = VERSION) -> bool:
    return version_key(candidate) > version_key(installed)


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )


def fetch_latest(
    api_url: str = LATEST_RELEASE_API,
    *,
    opener: Callable = urllib.request.urlopen,
    timeout: float = 15,
) -> ReleaseInfo:
    """Read GitHub's latest release and select its Setup executable."""
    try:
        with opener(_request(api_url), timeout=timeout) as response:
            payload = response.read(2 * 1024 * 1024 + 1)
    except (OSError, urllib.error.URLError) as exc:
        raise UpdateError("cannot_check", str(exc)) from exc
    if len(payload) > 2 * 1024 * 1024:
        raise UpdateError("invalid_release", "release response is too large")
    try:
        data = json.loads(payload.decode("utf-8"))
        raw_version = str(data["tag_name"]).strip()
        version_key(raw_version)
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise UpdateError("invalid_release", str(exc)) from exc
    version = raw_version[1:] if raw_version.lower().startswith("v") else raw_version
    expected = f"IL2_Korea_Service_Record_Setup_v{version}.exe"
    asset_data = next(
        (item for item in data.get("assets", []) if item.get("name") == expected),
        None,
    )
    if asset_data is None:
        raise UpdateError("asset_missing", expected)
    try:
        asset = ReleaseAsset(
            name=expected,
            url=str(asset_data["browser_download_url"]),
            size=int(asset_data["size"]),
            digest=str(asset_data.get("digest") or ""),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise UpdateError("invalid_release", str(exc)) from exc
    return ReleaseInfo(
        version=version,
        published_at=str(data.get("published_at") or ""),
        notes=str(data.get("body") or ""),
        html_url=str(data.get("html_url") or ""),
        asset=asset,
    )


def _powershells() -> list[str]:
    candidates: list[str] = []
    for name in ("pwsh.exe", "pwsh"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    built_in = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if built_in.is_file():
        candidates.append(str(built_in))
    found = shutil.which("powershell.exe") or shutil.which("powershell")
    if found:
        candidates.append(found)
    unique = list(dict.fromkeys(os.path.normcase(item) for item in candidates))
    if not unique:
        raise UpdateError("signature_tool", "PowerShell was not found")
    return unique


def authenticode_signature(path: Path) -> SignatureInfo:
    """Return Authenticode status and the signer's durable profile identity."""
    script = (
        "$ErrorActionPreference='Stop';"
        "$s=Get-AuthenticodeSignature -LiteralPath $env:IL2K_UPDATE_SIGNATURE_PATH;"
        "$thumb='';$subject='';$profileEku='';"
        "if($s.SignerCertificate){$thumb=$s.SignerCertificate.Thumbprint;"
        "$subject=$s.SignerCertificate.Subject;"
        "$profileEkus=@($s.SignerCertificate.EnhancedKeyUsageList|"
        "ForEach-Object{[string]$_.ObjectId}|"
        "Where-Object{$_ -like '1.3.6.1.4.1.311.97.*' -and "
        "$_ -ne '1.3.6.1.4.1.311.97.1.0'});"
        "if($profileEkus.Count -gt 0){$profileEku=[string]$profileEkus[0]}};"
        "[pscustomobject]@{Status=[string]$s.Status;Thumbprint=$thumb;"
        "Subject=$subject;ProfileEku=$profileEku}|ConvertTo-Json -Compress"
    )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    environment = os.environ.copy()
    environment["IL2K_UPDATE_SIGNATURE_PATH"] = str(path.resolve())
    errors: list[str] = []
    for executable in _powershells():
        try:
            done = subprocess.run(
                [executable, "-NoLogo", "-NoProfile", "-NonInteractive",
                 "-Command", script],
                capture_output=True, text=True, timeout=30,
                creationflags=flags, check=False, env=environment,
            )
            if done.returncode:
                errors.append(done.stderr.strip() or f"exit code {done.returncode}")
                continue
            data = json.loads(done.stdout.lstrip("\ufeff").strip())
            return SignatureInfo(
                status=str(data.get("Status") or ""),
                thumbprint=str(data.get("Thumbprint") or ""),
                subject=str(data.get("Subject") or ""),
                profile_eku=str(data.get("ProfileEku") or ""),
            )
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            errors.append(str(exc))
    raise UpdateError("signature_tool", " | ".join(errors))


def _expected_digest(value: str) -> str:
    match = re.fullmatch(r"sha256:([0-9a-fA-F]{64})", value.strip())
    if not match:
        raise UpdateError("digest_missing", value or "no digest")
    return match.group(1).lower()


def _same_signing_identity(left: SignatureInfo, right: SignatureInfo) -> bool:
    """Compare the durable Artifact Signing profile, with a legacy fallback.

    Artifact Signing renews its short-lived leaf certificate every day.  The
    profile-specific EKU stays stable for the lifetime of the signing profile
    and is the value Microsoft provides for durable identity pinning.  Exact
    thumbprints remain useful for conventional certificates without that EKU.
    """
    def durable_eku(value: str) -> str:
        value = value.strip()
        if (
            value.startswith(ARTIFACT_SIGNING_EKU_PREFIX)
            and value != ARTIFACT_SIGNING_PUBLIC_TRUST_EKU
        ):
            return value
        return ""

    left_eku = durable_eku(left.profile_eku)
    right_eku = durable_eku(right.profile_eku)
    if left_eku or right_eku:
        return bool(left_eku and right_eku and left_eku == right_eku)
    left_thumb = left.thumbprint.replace(" ", "").upper()
    right_thumb = right.thumbprint.replace(" ", "").upper()
    return bool(left_thumb and left_thumb == right_thumb)


def download_and_verify(
    release: ReleaseInfo,
    *,
    signature_source: Optional[Path] = None,
    destination: Optional[Path] = None,
    opener: Callable = urllib.request.urlopen,
    signature_reader: Callable[[Path], SignatureInfo] = authenticode_signature,
    progress: Optional[Callable[[str, int, int], None]] = None,
) -> Path:
    """Download Setup and require both GitHub's digest and our signer."""
    expected = _expected_digest(release.asset.digest)
    destination = destination or Path(tempfile.gettempdir()) / release.asset.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f".{destination.stem}.download.exe")
    digest = hashlib.sha256()
    received = 0
    try:
        with opener(_request(release.asset.url), timeout=60) as response, partial.open("wb") as out:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                out.write(block)
                digest.update(block)
                received += len(block)
                if release.asset.size >= 0 and received > release.asset.size:
                    raise UpdateError(
                        "size_mismatch",
                        f"{received} > {release.asset.size}",
                    )
                if progress:
                    progress("downloading", received, release.asset.size)
        if release.asset.size >= 0 and received != release.asset.size:
            raise UpdateError("size_mismatch", f"{received} != {release.asset.size}")
        if progress:
            progress("verifying_hash", received, release.asset.size)
        actual = digest.hexdigest()
        if actual != expected:
            raise UpdateError("digest_mismatch", f"{actual} != {expected}")

        if progress:
            progress("verifying_signature", received, release.asset.size)
        source = signature_source or Path(sys.executable)
        running = signature_reader(Path(source))
        downloaded = signature_reader(partial)
        if running.status.lower() != "valid" or not (
            running.profile_eku or running.thumbprint
        ):
            raise UpdateError("running_unsigned", running.status)
        if downloaded.status.lower() != "valid" or not (
            downloaded.profile_eku or downloaded.thumbprint
        ):
            raise UpdateError("signature_invalid", downloaded.status)
        if not _same_signing_identity(downloaded, running):
            raise UpdateError(
                "signer_mismatch",
                f"{downloaded.profile_eku or downloaded.thumbprint} != "
                f"{running.profile_eku or running.thumbprint}",
            )
        os.replace(partial, destination)
        return destination
    except UpdateError:
        partial.unlink(missing_ok=True)
        raise
    except (OSError, urllib.error.URLError) as exc:
        partial.unlink(missing_ok=True)
        raise UpdateError("download_failed", str(exc)) from exc


def process_running(image_name: str) -> bool:
    """Ask Windows for an exact executable image name."""
    if os.name != "nt":
        return False
    tasklist = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tasklist.exe"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = subprocess.run(
            [str(tasklist), "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10,
            creationflags=flags, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateError("process_check", str(exc)) from exc
    if done.returncode:
        raise UpdateError("process_check", done.stderr.strip())
    return any(
        row and row[0].casefold() == image_name.casefold()
        for row in csv.reader(done.stdout.splitlines())
    )


def _tracker_ping(base_url: str, opener: Callable, timeout: float = 1.0) -> bool:
    try:
        with opener(_request(base_url.rstrip("/") + "/api/ping"), timeout=timeout) as response:
            return json.load(response).get("app") == "korea-service-record"
    except (OSError, urllib.error.URLError, ValueError):
        return False


def stop_tracker(
    base_url: str = "http://127.0.0.1:5002",
    *,
    opener: Callable = urllib.request.urlopen,
    timeout: float = 12,
) -> bool:
    """Close the tracker without letting it terminate this Helper process."""
    if not _tracker_ping(base_url, opener):
        return True
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/update-shutdown",
        data=b"",
        method="POST",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with opener(request, timeout=3) as response:
            if response.status >= 300:
                return False
    except (OSError, urllib.error.URLError):
        return False
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if not _tracker_ping(base_url, opener):
            return True
        time.sleep(0.2)
    return False


def launch_installer(
    installer: Path,
    *,
    process_check: Callable[[str], bool] = process_running,
    tracker_stop: Callable[[], bool] = stop_tracker,
    launcher: Callable = subprocess.Popen,
) -> object:
    """Close the running applications and start Setup in update mode."""
    if process_check("IL2Series.exe"):
        raise UpdateError("game_running")
    if not tracker_stop():
        raise UpdateError("tracker_running")
    # Its HTTP listener closes before the tray process reaches os._exit().
    # Give that orderly shutdown time to release the installed files.
    until = time.monotonic() + 8
    while process_check("IL2_Korea_Service_Record.exe"):
        if time.monotonic() >= until:
            raise UpdateError("tracker_running")
        time.sleep(0.2)
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        return launcher(
            [str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
            close_fds=True,
            creationflags=flags,
        )
    except OSError as exc:
        raise UpdateError("install_failed", str(exc)) from exc
