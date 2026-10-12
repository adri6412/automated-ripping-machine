"""Builders for synthetic disc structures used by the tests and the UI demo."""
from __future__ import annotations

import os
import struct
from pathlib import Path


# ---------------------------------------------------------------- Blu-ray
def make_mpls(items: list[tuple[str, float]], chapters: int = 0) -> bytes:
    """items: (clip name, seconds)."""
    body = b""
    t = 0
    for clip, secs in items:
        in_t, out_t = t, t + int(secs * 45000)
        item = clip.encode() + b"M2TS" + struct.pack(">HBII", 0, 0, in_t, out_t) + b"\x00" * 12
        body += struct.pack(">H", len(item)) + item
    playlist = struct.pack(">HHH", 0, len(items), 0) + body
    playlist = struct.pack(">I", len(playlist)) + playlist
    marks = b"".join(struct.pack(">BBHIHI", 0, 1, 0, i * 45000 * 600, 0xFFFF, 0)
                     for i in range(chapters))
    mark_block = struct.pack(">IH", 2 + len(marks), chapters) + marks
    pl_start = 40
    mark_start = pl_start + len(playlist)
    header = b"MPLS0200" + struct.pack(">III", pl_start, mark_start, 0)
    header += b"\x00" * (pl_start - len(header))
    return header + playlist + mark_block


def ts_unit(encrypted: bool) -> bytes:
    unit = bytearray()
    for _ in range(32):
        pkt = bytearray(os.urandom(192))
        pkt[4] = 0x47
        unit += pkt
    if encrypted:
        unit[16:] = os.urandom(len(unit) - 16)
        # make sure we don't accidentally produce many sync bytes
        for i in range(1, 32):
            if unit[i * 192 + 4] == 0x47:
                unit[i * 192 + 4] = 0x48
    return bytes(unit)


def make_bluray(root: Path, encrypted: bool = False, uhd: bool = False) -> Path:
    (root / "BDMV" / "PLAYLIST").mkdir(parents=True)
    (root / "BDMV" / "STREAM").mkdir(parents=True)
    (root / "BDMV" / "META" / "DL").mkdir(parents=True)
    (root / "CERTIFICATE").mkdir()
    (root / "BDMV" / "index.bdmv").write_bytes(b"INDX" + (b"0300" if uhd else b"0200") + b"\0" * 32)
    (root / "BDMV" / "PLAYLIST" / "00000.mpls").write_bytes(make_mpls([("00001", 95)]))
    (root / "BDMV" / "PLAYLIST" / "00800.mpls").write_bytes(
        make_mpls([("00010", 3600), ("00011", 2400)], chapters=24))
    # obfuscation decoy: same clip repeated
    (root / "BDMV" / "PLAYLIST" / "00900.mpls").write_bytes(
        make_mpls([("00012", 1000)] * 8, chapters=3))
    for clip, units in (("00001", 4), ("00010", 40), ("00011", 30), ("00012", 6)):
        (root / "BDMV" / "STREAM" / f"{clip}.m2ts").write_bytes(
            b"".join(ts_unit(encrypted) for _ in range(units)))
    (root / "BDMV" / "META" / "DL" / "bdmt_eng.xml").write_text(
        '<disclib><di:discinfo><di:title><di:name>Test Movie</di:name></di:title>'
        '</di:discinfo></disclib>', encoding="utf-8")
    return root


# ---------------------------------------------------------------- DVD
def _bcd(n: int) -> int:
    return (n // 10) << 4 | (n % 10)


def bcd_time(seconds: int) -> bytes:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return bytes([_bcd(h), _bcd(m), _bcd(s), 0x40])   # 25 fps, 0 frames


def make_vmg(titles: list[tuple[int, int, int]]) -> bytes:
    """titles: (vts, vts_ttn, chapters)"""
    data = bytearray(4096)
    data[0:12] = b"DVDVIDEO-VMG"
    struct.pack_into(">I", data, 0xC4, 1)
    base = 2048
    struct.pack_into(">HHI", data, base, len(titles), 0, 8 + 12 * len(titles) - 1)
    for i, (vts, ttn, chapters) in enumerate(titles):
        struct.pack_into(">BBHHBBI", data, base + 8 + 12 * i, 0x3C, 1, chapters, 0, vts, ttn, 0)
    return bytes(data)


def make_vts(title_pgcs: list[list[int]], pgc_seconds: list[int]) -> bytes:
    data = bytearray(3 * 2048)
    data[0:12] = b"DVDVIDEO-VTS"
    struct.pack_into(">I", data, 0xC8, 1)
    struct.pack_into(">I", data, 0xCC, 2)
    ptt = 2048
    n = len(title_pgcs)
    off = 8 + 4 * n
    offsets = []
    entries = b""
    for pgcs in title_pgcs:
        offsets.append(off + len(entries))
        entries += b"".join(struct.pack(">HH", pg, 1) for pg in pgcs)
    struct.pack_into(">HHI", data, ptt, n, 0, off + len(entries) - 1)
    for i, o in enumerate(offsets):
        struct.pack_into(">I", data, ptt + 8 + 4 * i, o)
    data[ptt + off:ptt + off + len(entries)] = entries
    pgci = 4096
    struct.pack_into(">HHI", data, pgci, len(pgc_seconds), 0, 0)
    pgc_area = 8 + 8 * len(pgc_seconds)
    for i, secs in enumerate(pgc_seconds):
        pgc_off = pgc_area + i * 16
        struct.pack_into(">II", data, pgci + 8 + 8 * i, 0x81000000, pgc_off)
        data[pgci + pgc_off + 4:pgci + pgc_off + 8] = bcd_time(secs)
    return bytes(data)


def vob_sector(scrambled: bool) -> bytes:
    sec = bytearray(2048)
    sec[0:4] = b"\x00\x00\x01\xba"
    sec[4] = 0x44                       # MPEG-2 marker
    sec[13] = 0xF8                      # no stuffing
    pes = 14
    sec[pes:pes + 4] = b"\x00\x00\x01\xe0"
    struct.pack_into(">H", sec, pes + 4, 2048 - pes - 6)
    sec[pes + 6] = 0x80 | (0x10 if scrambled else 0)
    sec[pes + 7] = 0x80
    sec[pes + 8] = 5
    return bytes(sec)


def make_dvd(root: Path, scrambled: bool = False) -> Path:
    vts = root / "VIDEO_TS"
    vts.mkdir(parents=True)
    (vts / "VIDEO_TS.IFO").write_bytes(make_vmg([(1, 1, 2), (2, 1, 28), (2, 2, 1)]))
    (vts / "VTS_01_0.IFO").write_bytes(make_vts([[1]], [120]))
    (vts / "VTS_02_0.IFO").write_bytes(make_vts([[1, 2], [3]], [3000, 2700, 60]))
    (vts / "VTS_01_1.VOB").write_bytes(vob_sector(False) * 50)
    (vts / "VTS_02_1.VOB").write_bytes(vob_sector(scrambled) * 400)
    (root / "AUDIO_TS").mkdir()
    return root
