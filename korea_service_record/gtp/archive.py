"""
Reader for IL-2 Korea "gtpack" archives (``.gtp``).

Container layout::

    0x00  "S16E!" encrypted  |  "S16R!" plain
    0x30  u64  entry count (authoritative — do not trust 0x28)
    0x40  FAT: exactly `count` packed records

FAT record (32-byte fixed part, then the name inline)::

    +0x00 tag "DIR!" or "FILE"      +0x10 u32 timestamp
    +0x04 u32 version               +0x14 u32 parent dir index
    +0x08 u32 offset -> STRMFILE    +0x18 u64 name length (incl. NUL)
    +0x0C u32 size                  +0x20 char[] full virtual path

Payload::

    [offset]      "STRMFILE" + u64 size + padding   (32-byte header)
    [offset + 32] `size` bytes, ciphertext in an S16E! archive

Difference from the standalone extractor
----------------------------------------
``il2k_extract.py`` slurps the whole remainder of the file to walk the FAT,
which is fine for a batch unpack but not here: ``Interface.gtp`` is 1.6 GB and
the tracker only wants a handful of small files out of it. This reader walks
the FAT in bounded chunks and seeks straight to the one payload it needs, so
pulling a locale file costs a few hundred KB of I/O instead of the whole
archive.
"""

import logging
import os
import struct
from pathlib import Path
from typing import Iterator, NamedTuple, Optional

from .crypto import decrypt_ecb, derive_key, path_hash

logger = logging.getLogger(__name__)

FAT_START = 0x40
RECORD_FIXED = 32
CHUNK = 1 << 20          # 1 MB of FAT at a time; a record is rarely > 300 bytes
STRMFILE_HEADER = 32


class Entry(NamedTuple):
    vpath: str           # full virtual path, e.g. "/nsdata/assets/locale/ranks.locale=eng.json"
    offset: int
    size: int

    @property
    def name(self) -> str:
        return self.vpath.rsplit("/", 1)[-1]


class GtpArchive:
    """Random-access reader for one ``.gtp``."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._fh = open(self.path, "rb")
        head = self._fh.read(FAT_START)
        self.magic = head[:5]
        if self.magic not in (b"S16E!", b"S16R!"):
            self._fh.close()
            raise ValueError(f"{self.path.name}: not a gtpack archive "
                             f"(magic {self.magic!r})")
        self.encrypted = self.magic == b"S16E!"
        self.count = struct.unpack_from("<Q", head, 0x30)[0]

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()

    def __enter__(self) -> "GtpArchive":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- FAT ---------------------------------------------------------------

    def entries(self) -> Iterator[Entry]:
        """
        Yield every FILE record, reading the FAT in bounded chunks.

        Records are variable length, so the buffer is topped up whenever the
        next record would straddle its end.
        """
        self._fh.seek(FAT_START)
        buf = self._fh.read(CHUNK)
        pos = 0
        for _ in range(self.count):
            # Ensure the fixed part plus the name are resident.
            if len(buf) - pos < RECORD_FIXED:
                buf = buf[pos:] + self._fh.read(CHUNK)
                pos = 0
                if len(buf) < RECORD_FIXED:
                    logger.warning("%s: FAT truncated", self.path.name)
                    return
            name_len = struct.unpack_from("<Q", buf, pos + 24)[0]
            need = RECORD_FIXED + name_len
            if len(buf) - pos < need:
                buf = buf[pos:] + self._fh.read(max(CHUNK, need))
                pos = 0
                if len(buf) < need:
                    logger.warning("%s: FAT truncated mid-record", self.path.name)
                    return

            tag = buf[pos:pos + 4]
            offset, size = struct.unpack_from("<II", buf, pos + 8)
            vpath = buf[pos + RECORD_FIXED:pos + RECORD_FIXED + name_len - 1] \
                .decode("utf-8", "replace")
            pos += need

            if tag == b"FILE":
                yield Entry(vpath, offset, size)
            elif tag != b"DIR!":
                logger.warning("%s: unexpected record tag %r", self.path.name, tag)
                return

    def find(self, vpath: str) -> Optional[Entry]:
        """Locate one entry by exact virtual path, case-insensitively."""
        wanted = vpath.lower().lstrip("/")
        for entry in self.entries():
            if entry.vpath.lower().lstrip("/") == wanted:
                return entry
        return None

    # -- payload -----------------------------------------------------------

    def read(self, entry: Entry) -> bytes:
        """
        Read and, if needed, decrypt one entry.

        The key derives from the entry's own virtual path, so it must be passed
        exactly as stored. Only the final partial block needs the extra read:
        the archive stores a whole padded block, so extraction is exact.
        """
        self._fh.seek(entry.offset)
        if self._fh.read(8) != b"STRMFILE":
            raise ValueError(f"{entry.vpath}: STRMFILE header missing "
                             f"at {entry.offset}")
        self._fh.seek(entry.offset + STRMFILE_HEADER)
        raw = self._fh.read(entry.size)
        if not self.encrypted:
            return raw

        key = derive_key(path_hash(entry.vpath.lower()))
        whole = len(raw) // 16 * 16
        out = decrypt_ecb(raw, key)
        if whole < entry.size:
            self._fh.seek(entry.offset + STRMFILE_HEADER + whole)
            out += decrypt_ecb(self._fh.read(16), key)[:entry.size - whole]
        return out

    def extract(self, vpath: str) -> Optional[bytes]:
        entry = self.find(vpath)
        if entry is None:
            return None
        return self.read(entry)


def find_archives(game_dir: Path) -> list:
    """Every ``.gtp`` under ``<game_dir>/data``."""
    data = Path(game_dir) / "data"
    if not data.is_dir():
        return []
    return sorted(data.glob("*.gtp"))
