"""Builders for synthetic discs and a fake ``makemkvcon`` used by the tests and the UI demo."""
from __future__ import annotations

import stat
import sys
from pathlib import Path


def make_bluray(root: Path, uhd: bool = False) -> Path:
    (root / "BDMV" / "PLAYLIST").mkdir(parents=True)
    (root / "BDMV" / "STREAM").mkdir(parents=True)
    (root / "BDMV" / "META" / "DL").mkdir(parents=True)
    (root / "CERTIFICATE").mkdir()
    (root / "BDMV" / "index.bdmv").write_bytes(b"INDX" + (b"0300" if uhd else b"0200") + b"\0" * 32)
    (root / "BDMV" / "PLAYLIST" / "00800.mpls").write_bytes(b"MPLS0200" + b"\0" * 64)
    (root / "BDMV" / "STREAM" / "00010.m2ts").write_bytes(b"\0" * 192 * 64)
    (root / "BDMV" / "META" / "DL" / "bdmt_eng.xml").write_text(
        '<disclib><di:discinfo><di:title><di:name>Test Movie</di:name></di:title>'
        '</di:discinfo></disclib>', encoding="utf-8")
    return root


def make_dvd(root: Path) -> Path:
    vts = root / "VIDEO_TS"
    vts.mkdir(parents=True)
    (vts / "VIDEO_TS.IFO").write_bytes(b"DVDVIDEO-VMG" + b"\0" * 2036)
    (vts / "VTS_01_1.VOB").write_bytes(b"\0" * 2048 * 4)
    (root / "AUDIO_TS").mkdir()
    return root


# Robot-mode output of "makemkvcon -r info disc:0" for a Blu-ray with a decoy playlist.
MAKEMKV_INFO = r'''MSG:1005,0,1,"MakeMKV v1.18.1 win(x64-release) started","%1 started","MakeMKV v1.18.1 win(x64-release)"
DRV:0,2,999,12,"BD-RE HL-DT-ST BD-RE  WH16NS60 1.02","TEST_MOVIE","D:"
DRV:1,256,999,0,"","",""
PRGT:5018,0,"Scanning CD-ROM devices"
PRGV:0,65536,65536
MSG:3307,0,2,"File 00800.mpls was added as title #0","File %1 was added as title #%2","00800.mpls","0"
TCOUT:3
CINFO:1,6209,"Blu-ray disc"
CINFO:2,0,"Test Movie"
CINFO:32,0,"TEST_MOVIE"
TINFO:0,2,0,"Test Movie"
TINFO:0,8,0,"24"
TINFO:0,9,0,"1:40:00"
TINFO:0,10,0,"25.3 GB"
TINFO:0,11,0,"27166914560"
TINFO:0,16,0,"00800.mpls"
TINFO:0,25,0,"2"
TINFO:0,27,0,"Test_Movie_t00.mkv"
SINFO:0,0,1,6201,"Video"
TINFO:1,8,0,"3"
TINFO:1,9,0,"0:12:30"
TINFO:1,11,0,"2147483648"
TINFO:1,16,0,"00801.mpls"
TINFO:1,27,0,"Test_Movie_t01.mkv"
TINFO:2,8,0,"0"
TINFO:2,9,0,"1:39:59"
TINFO:2,11,0,"1073741824"
TINFO:2,16,0,"00900.mpls"
TINFO:2,27,0,"Test_Movie_t02.mkv"
MSG:5011,0,0,"Operation successfully completed","Operation successfully completed"
'''

_FAKE_MAKEMKVCON = r'''
import os, sys, time
args = [a for a in sys.argv[1:] if not a.startswith("-")]
INFO = {info!r}
if args[:2] == ["info", "disc:9999"]:
    print("\n".join(l for l in INFO.splitlines() if l.startswith(("MSG:1005", "DRV"))))
    sys.exit(0)
if args[0] == "info":
    print('PRGT:5003,0,"Opening Blu-ray disc"')
    for i in range(0, 65537, 16384):
        print(f'PRGC:5085,0,"Processing title sets"\nPRGV:{{i}},{{i}},65536', flush=True)
        time.sleep({delay})
    print(INFO)
    sys.exit(0)
if args[0] in ("mkv", "backup"):
    out = args[-1]
    os.makedirs(out, exist_ok=True)
    print('PRGT:5018,0,"Saving to MKV file"')
    for i in range(0, 65537, 8192):
        print(f'PRGC:5017,0,"Saving title"\nPRGV:{{i}},{{i}},65536', flush=True)
        time.sleep({delay})
    if args[0] == "backup":
        os.makedirs(os.path.join(out, "BDMV", "STREAM"), exist_ok=True)
        open(os.path.join(out, "BDMV", "index.bdmv"), "wb").write(b"INDX0200")
        print('MSG:5014,0,0,"Backup done","Backup done"')
    else:
        ids = ["0", "1", "2"] if args[2] == "all" else [args[2]]
        for t in ids:
            open(os.path.join(out, f"Test_Movie_t0{{t}}.mkv"), "wb").write(b"mkv")
        print(f'MSG:5036,0,2,"Copy complete. {{len(ids)}} titles saved.","Copy complete. %1 titles saved.","{{len(ids)}}"')
    sys.exit(0)
sys.exit(2)
'''


def fake_makemkvcon(directory: Path, delay: float = 0.0) -> str:
    """Write an executable fake makemkvcon (POSIX shebang) and return its path."""
    path = directory / "makemkvcon"
    path.write_text(f"#!{sys.executable}\n" + _FAKE_MAKEMKVCON.format(info=MAKEMKV_INFO, delay=delay))
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)
