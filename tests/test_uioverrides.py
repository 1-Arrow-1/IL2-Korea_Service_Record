"""uioverrides: warn when a game update changed a screen the mod replaces."""
import hashlib

from korea_service_record import uioverrides

VPATH = "nsdata/controls/career/career.rdict.xaml"


class FakeResolver:
    def __init__(self, tmp_path, archive: bytes, installed: bool):
        self.root, self.archive = tmp_path, archive
        if installed:
            loose = self._loose_path(VPATH)
            loose.parent.mkdir(parents=True)
            loose.write_bytes(b"mod copy")

    def _loose_path(self, vpath):
        return self.root / "data" / vpath

    def _extract(self, vpath):
        return self.archive if vpath == VPATH else None


def test_matching_original_is_not_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(uioverrides, "BASES", {VPATH: hashlib.sha256(b"1.004b").hexdigest()})
    assert uioverrides.stale(FakeResolver(tmp_path, b"1.004b", installed=True)) == []


def test_changed_original_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(uioverrides, "BASES", {VPATH: hashlib.sha256(b"1.004b").hexdigest()})
    assert uioverrides.stale(FakeResolver(tmp_path, b"1.005", installed=True)) == ["career.rdict.xaml"]


def test_override_not_installed_is_not_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(uioverrides, "BASES", {VPATH: hashlib.sha256(b"1.004b").hexdigest()})
    assert uioverrides.stale(FakeResolver(tmp_path, b"1.005", installed=False)) == []


def test_real_baselines_are_sha256():
    assert all(len(h) == 64 for h in uioverrides.BASES.values())
