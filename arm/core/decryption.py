"""Checks whether XReveal has finished decrypting a disc.

XReveal decrypts transparently at driver level a few seconds/minutes after
insertion. Until then the disc may be unreadable or return scrambled data.
Instead of trusting a fixed delay we inspect real content:

* DVD (CSS): every MPEG-2 PES header carries a ``PES_scrambling_control``
  field. Decrypting tools clear it, so a VOB sector with those bits set (or
  a read error on a protected sector) means "not yet".
* Blu-ray (AACS): a decrypted ``.m2ts`` is a sequence of 192-byte source
  packets whose 5th byte is the MPEG-TS sync byte ``0x47``. In an encrypted
  6144-byte aligned unit only the first 16 bytes are in clear, so the sync
  bytes of the following packets are random.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .disc import DiscInfo, DiscType

SECTOR = 2048
ALIGNED_UNIT = 6144
SOURCE_PACKET = 192
SAMPLES = 8

# PES stream ids that carry the optional PES header with scrambling bits.
_PES_WITH_HEADER = set(range(0xC0, 0xF0)) | {0xBD, 0xFD}


@dataclass
class CheckResult:
    ready: bool
    message: str


def _sample_offsets(size: int, block: int, samples: int = SAMPLES) -> list[int]:
    blocks = size // block
    if blocks <= 0:
        return []
    if blocks <= samples:
        return [i * block for i in range(blocks)]
    # Skip the first 2 % (often a clear intro/FBI warning) but always include block 0.
    offsets = {0}
    for i in range(1, samples):
        offsets.add(int(blocks * (0.02 + 0.96 * i / samples)) * block)
    return sorted(offsets)


def dvd_sector_scrambled(sector: bytes) -> bool | None:
    """True if a VOB sector is CSS scrambled, False if clear, None if unknown."""
    if len(sector) < SECTOR or sector[:4] != b"\x00\x00\x01\xba":
        return None
    if (sector[4] & 0xC0) == 0x40:                 # MPEG-2 pack header
        pos = 14 + (sector[13] & 0x07)
    else:                                         # MPEG-1 pack header
        pos = 12
    verdict = None
    while pos + 9 <= len(sector) and sector[pos:pos + 3] == b"\x00\x00\x01":
        stream_id = sector[pos + 3]
        length = int.from_bytes(sector[pos + 4:pos + 6], "big")
        if stream_id in _PES_WITH_HEADER and (sector[pos + 6] & 0xC0) == 0x80:
            if sector[pos + 6] & 0x30:
                return True
            verdict = False
        pos += 6 + length
    return verdict


def ts_unit_clear(unit: bytes) -> bool | None:
    """True if a 6144-byte BD aligned unit looks decrypted."""
    if len(unit) < ALIGNED_UNIT:
        return None
    packets = ALIGNED_UNIT // SOURCE_PACKET
    hits = sum(1 for i in range(packets) if unit[i * SOURCE_PACKET + 4] == 0x47)
    if hits >= packets - 1:
        return True
    if unit[4] != 0x47:
        return None                               # not a transport stream at all
    return False


def _largest(files: list[Path]) -> Path | None:
    best, best_size = None, -1
    for f in files:
        try:
            size = f.stat().st_size
        except OSError:
            continue
        if size > best_size:
            best, best_size = f, size
    return best


def _ci_dir(root: Path, *parts: str) -> Path | None:
    current = root
    for part in parts:
        try:
            current = next(c for c in current.iterdir() if c.name.upper() == part)
        except (OSError, StopIteration):
            return None
    return current


def check_dvd(root: Path) -> CheckResult:
    vdir = _ci_dir(root, "VIDEO_TS")
    if vdir is None:
        return CheckResult(False, "cartella VIDEO_TS non accessibile")
    try:
        all_vobs = [f for f in vdir.iterdir() if f.suffix.upper() == ".VOB"]
    except OSError as exc:
        return CheckResult(False, f"VIDEO_TS non leggibile ({exc.strerror or exc})")
    titles = [f for f in all_vobs if not f.name.upper().endswith("_0.VOB")]
    target = _largest(titles) or _largest(all_vobs)
    if target is None:
        return CheckResult(True, "nessun VOB da verificare")
    clear = scrambled = 0
    try:
        size = target.stat().st_size
        with open(target, "rb", buffering=0) as fh:
            for off in _sample_offsets(size, SECTOR, 16):
                fh.seek(off)
                verdict = dvd_sector_scrambled(fh.read(SECTOR))
                if verdict is True:
                    scrambled += 1
                elif verdict is False:
                    clear += 1
    except OSError as exc:
        return CheckResult(False, f"lettura {target.name} non riuscita ({exc.strerror or exc})")
    if scrambled:
        return CheckResult(False, f"{target.name}: {scrambled} settori ancora cifrati (CSS)")
    return CheckResult(True, f"{target.name}: {clear} settori verificati in chiaro")


def check_bluray(root: Path) -> CheckResult:
    sdir = _ci_dir(root, "BDMV", "STREAM")
    if sdir is None:
        return CheckResult(False, "cartella BDMV/STREAM non accessibile")
    try:
        m2ts = [f for f in sdir.iterdir() if f.suffix.upper() == ".M2TS"]
    except OSError as exc:
        return CheckResult(False, f"BDMV/STREAM non leggibile ({exc.strerror or exc})")
    target = _largest(m2ts)
    if target is None:
        return CheckResult(False, "nessun file .m2ts visibile")
    clear = encrypted = 0
    try:
        size = target.stat().st_size
        with open(target, "rb", buffering=0) as fh:
            for off in _sample_offsets(size, ALIGNED_UNIT):
                fh.seek(off)
                verdict = ts_unit_clear(fh.read(ALIGNED_UNIT))
                if verdict is True:
                    clear += 1
                elif verdict is False:
                    encrypted += 1
    except OSError as exc:
        return CheckResult(False, f"lettura {target.name} non riuscita ({exc.strerror or exc})")
    if encrypted or not clear:
        return CheckResult(False, f"{target.name}: dati ancora cifrati (AACS)")
    return CheckResult(True, f"{target.name}: {clear} blocchi verificati in chiaro")


def check(info: DiscInfo) -> CheckResult:
    if os.environ.get("ARM_SIM_DECRYPTED") == "0":
        return CheckResult(False, "simulazione: disco cifrato")
    if info.type == DiscType.DVD_VIDEO:
        return check_dvd(info.root)
    if info.type in (DiscType.BLURAY, DiscType.UHD_BLURAY):
        return check_bluray(info.root)
    return CheckResult(True, "nessuna decifratura necessaria")
