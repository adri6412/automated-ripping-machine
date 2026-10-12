"""Blu-ray structure helpers: MPLS playlist parsing and main-title selection."""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Playlist:
    path: Path
    duration: float                      # seconds
    clips: list[str] = field(default_factory=list)
    chapters: int = 0
    size: int = 0                        # bytes of referenced clips (unique)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def unique_ratio(self) -> float:
        return len(set(self.clips)) / len(self.clips) if self.clips else 0.0


def parse_mpls(data: bytes) -> tuple[float, list[str], int]:
    """Return (duration seconds, clip names, chapter count) of an MPLS file."""
    if len(data) < 20 or data[:4] != b"MPLS":
        raise ValueError("not an MPLS file")
    playlist_start, mark_start = struct.unpack_from(">II", data, 8)
    n_items = struct.unpack_from(">H", data, playlist_start + 6)[0]
    pos = playlist_start + 10
    clips: list[str] = []
    ticks = 0
    for _ in range(n_items):
        length = struct.unpack_from(">H", data, pos)[0]
        clip = data[pos + 2:pos + 7].decode("ascii", "replace")
        in_time, out_time = struct.unpack_from(">II", data, pos + 14)
        clips.append(clip)
        ticks += max(0, out_time - in_time)
        pos += 2 + length
    chapters = 0
    if 0 < mark_start + 6 <= len(data):
        n_marks = struct.unpack_from(">H", data, mark_start + 4)[0]
        for i in range(n_marks):
            off = mark_start + 6 + i * 14
            if off + 2 <= len(data) and data[off + 1] == 1:   # mark_type 1 = entry mark
                chapters += 1
    return ticks / 45000.0, clips, chapters


def scan_playlists(root: Path) -> list[Playlist]:
    pl_dir = root / "BDMV" / "PLAYLIST"
    stream_dir = root / "BDMV" / "STREAM"
    result = []
    if not pl_dir.is_dir():
        return result
    for f in sorted(pl_dir.iterdir()):
        if f.suffix.lower() != ".mpls":
            continue
        try:
            duration, clips, chapters = parse_mpls(f.read_bytes())
        except (OSError, ValueError, struct.error):
            continue
        size = 0
        for clip in set(clips):
            try:
                size += (stream_dir / f"{clip}.m2ts").stat().st_size
            except OSError:
                pass
        result.append(Playlist(f, duration, clips, chapters, size))
    return result


def pick_main_playlist(playlists: list[Playlist], min_seconds: float = 0) -> Playlist | None:
    """Choose the feature playlist.

    Prefers the longest playlist whose clips are not heavily repeated (a
    common obfuscation trick), falling back to the plain longest one.
    """
    if not playlists:
        return None
    sane = [p for p in playlists if p.unique_ratio >= 0.5 and p.duration >= min_seconds]
    pool = sane or playlists
    # Round to 1 s so near-identical decoys are decided by size/number of chapters.
    return max(pool, key=lambda p: (round(p.duration), p.size, p.chapters))


def disc_title(root: Path) -> str | None:
    """Read the human-friendly title from BDMV/META/DL/bdmt_*.xml if present."""
    meta = root / "BDMV" / "META" / "DL"
    if not meta.is_dir():
        return None
    files = sorted(meta.glob("bdmt_*.xml"), key=lambda p: (p.name != "bdmt_ita.xml",
                                                          p.name != "bdmt_eng.xml", p.name))
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(r"<di:name>(.*?)</di:name>", text, re.S)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return None


def is_uhd(root: Path) -> bool:
    try:
        with open(root / "BDMV" / "index.bdmv", "rb") as fh:
            header = fh.read(8)
    except OSError:
        return False
    return header[4:8] == b"0300"
