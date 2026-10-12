"""DVD-Video IFO parsing (title list with durations) for main-title selection."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

SECTOR = 2048


@dataclass
class DvdTitle:
    number: int          # global title number (1-based, as used by ffmpeg -title)
    vts: int
    vts_ttn: int
    chapters: int
    angles: int
    duration: float      # seconds


def _bcd(b: int) -> int:
    return (b >> 4) * 10 + (b & 0x0F)


def bcd_time(raw: bytes) -> float:
    hours, minutes, seconds, frame = raw[0], raw[1], raw[2], raw[3]
    rate = {1: 25.0, 3: 29.97}.get(frame >> 6, 25.0)
    return _bcd(hours) * 3600 + _bcd(minutes) * 60 + _bcd(seconds) + _bcd(frame & 0x3F) / rate


def parse_vmg(data: bytes) -> list[tuple[int, int, int, int, int]]:
    """Return (title_no, vts, vts_ttn, chapters, angles) for every title in VIDEO_TS.IFO."""
    if data[:12] != b"DVDVIDEO-VMG":
        raise ValueError("not a VMG IFO")
    base = struct.unpack_from(">I", data, 0xC4)[0] * SECTOR
    n_titles = struct.unpack_from(">H", data, base)[0]
    titles = []
    for i in range(n_titles):
        off = base + 8 + i * 12
        _type, angles, chapters, _pm, vts, ttn = struct.unpack_from(">BBHHBB", data, off)
        titles.append((i + 1, vts, ttn, chapters, angles))
    return titles


def parse_vts_durations(data: bytes) -> dict[int, float]:
    """Return {vts_ttn: duration seconds} for one VTS_xx_0.IFO."""
    if data[:12] != b"DVDVIDEO-VTS":
        raise ValueError("not a VTS IFO")
    ptt_base = struct.unpack_from(">I", data, 0xC8)[0] * SECTOR
    pgci_base = struct.unpack_from(">I", data, 0xCC)[0] * SECTOR

    n_pgc = struct.unpack_from(">H", data, pgci_base)[0]
    pgc_durations = []
    for i in range(n_pgc):
        pgc_off = struct.unpack_from(">I", data, pgci_base + 8 + i * 8 + 4)[0]
        pgc_durations.append(bcd_time(data[pgci_base + pgc_off + 4:pgci_base + pgc_off + 8]))

    n_ttu, _res, end = struct.unpack_from(">HHI", data, ptt_base)
    offsets = [struct.unpack_from(">I", data, ptt_base + 8 + i * 4)[0] for i in range(n_ttu)]
    result = {}
    for i, off in enumerate(offsets):
        stop = offsets[i + 1] if i + 1 < n_ttu else end + 1
        pgcns: list[int] = []
        for p in range(off, stop - 3, 4):
            pgcn = struct.unpack_from(">H", data, ptt_base + p)[0]
            if pgcn not in pgcns:
                pgcns.append(pgcn)
        result[i + 1] = sum(pgc_durations[n - 1] for n in pgcns if 0 < n <= len(pgc_durations))
    return result


def scan_titles(root: Path) -> list[DvdTitle]:
    vts_dir = root / "VIDEO_TS"
    vmg = parse_vmg((vts_dir / "VIDEO_TS.IFO").read_bytes())
    cache: dict[int, dict[int, float]] = {}
    titles = []
    for number, vts, ttn, chapters, angles in vmg:
        if vts not in cache:
            try:
                cache[vts] = parse_vts_durations((vts_dir / f"VTS_{vts:02d}_0.IFO").read_bytes())
            except (OSError, ValueError, struct.error):
                cache[vts] = {}
        titles.append(DvdTitle(number, vts, ttn, chapters, angles, cache[vts].get(ttn, 0.0)))
    return titles


def pick_main_title(titles: list[DvdTitle]) -> DvdTitle | None:
    if not titles:
        return None
    return max(titles, key=lambda t: (round(t.duration), t.chapters))
