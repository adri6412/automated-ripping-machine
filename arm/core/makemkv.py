"""MakeMKV command line (makemkvcon) integration.

makemkvcon decrypts DVDs (CSS) and Blu-rays/UHDs (AACS/BD+) by itself and is
driven in robot mode (``-r``), whose line based output is parsed here:

    DRV:index,state,unused,flags,"drive name","disc name","device"
    TCOUT:count
    CINFO:attr,code,"value"
    TINFO:title,attr,code,"value"
    SINFO:title,stream,attr,code,"value"
    MSG:code,flags,count,"message","format",params...
    PRGT:code,id,"name"   PRGC:code,id,"name"   PRGV:current,total,max
"""
from __future__ import annotations

import re
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass, field

# Attribute ids from MakeMKV's apdefs.h (AP_ItemAttributeId)
ATTR_TYPE = 1
ATTR_NAME = 2
ATTR_CHAPTERS = 8
ATTR_DURATION = 9
ATTR_SIZE = 10
ATTR_SIZE_BYTES = 11
ATTR_SOURCE_FILE = 16
ATTR_SEGMENTS_COUNT = 25
ATTR_OUTPUT_FILE = 27
ATTR_VOLUME_NAME = 32

DRIVE_STATE_MEDIA = 2

BETA_KEY_URL = "https://forum.makemkv.com/forum/viewtopic.php?t=1053"
KEY_PROBLEM_RE = re.compile(r"too old|expired|registration key|evaluation period", re.I)


def parse_fields(payload: str) -> list[str]:
    """Split a robot-mode payload on commas, honouring quoted strings with escapes."""
    fields: list[str] = []
    buf: list[str] = []
    in_quotes = False
    i = 0
    while i < len(payload):
        ch = payload[i]
        if in_quotes:
            if ch == "\\" and i + 1 < len(payload):
                buf.append(payload[i + 1])
                i += 1
            elif ch == '"':
                in_quotes = False
            else:
                buf.append(ch)
        elif ch == '"':
            in_quotes = True
        elif ch == ",":
            fields.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    fields.append("".join(buf))
    return fields


def parse_line(line: str) -> tuple[str, list[str]] | None:
    m = re.match(r"^([A-Z]{3,5}):(.*)$", line.strip())
    if not m:
        return None
    return m.group(1), parse_fields(m.group(2))


def parse_duration(text: str) -> float:
    parts = [p for p in text.strip().split(":") if p]
    try:
        values = [float(p) for p in parts]
    except ValueError:
        return 0.0
    seconds = 0.0
    for v in values:
        seconds = seconds * 60 + v
    return seconds


@dataclass
class Drive:
    index: int
    state: int
    drive_name: str
    disc_name: str
    device: str

    @property
    def has_media(self) -> bool:
        return self.state == DRIVE_STATE_MEDIA


@dataclass
class Title:
    id: int
    name: str = ""
    duration: float = 0.0
    chapters: int = 0
    size_bytes: int = 0
    size: str = ""
    source_file: str = ""
    output_file: str = ""
    segments: int = 0


@dataclass
class DiscScan:
    disc_type: str = ""
    name: str = ""
    volume_name: str = ""
    titles: list[Title] = field(default_factory=list)
    drives: list[Drive] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def main_title(self) -> Title | None:
        return pick_main_title(self.titles)


def parse_output(lines) -> DiscScan:
    scan = DiscScan()
    titles: dict[int, Title] = {}
    for line in lines:
        parsed = parse_line(line)
        if not parsed:
            continue
        kind, f = parsed
        try:
            if kind == "DRV" and len(f) >= 7:
                scan.drives.append(Drive(int(f[0]), int(f[1]), f[4], f[5], f[6]))
            elif kind == "CINFO" and len(f) >= 3:
                attr = int(f[0])
                if attr == ATTR_TYPE:
                    scan.disc_type = f[2]
                elif attr == ATTR_NAME:
                    scan.name = f[2]
                elif attr == ATTR_VOLUME_NAME:
                    scan.volume_name = f[2]
            elif kind == "TINFO" and len(f) >= 4:
                tid, attr, value = int(f[0]), int(f[1]), f[3]
                t = titles.setdefault(tid, Title(tid))
                if attr == ATTR_NAME:
                    t.name = value
                elif attr == ATTR_DURATION:
                    t.duration = parse_duration(value)
                elif attr == ATTR_CHAPTERS:
                    t.chapters = int(value or 0)
                elif attr == ATTR_SIZE_BYTES:
                    t.size_bytes = int(value or 0)
                elif attr == ATTR_SIZE:
                    t.size = value
                elif attr == ATTR_SOURCE_FILE:
                    t.source_file = value
                elif attr == ATTR_OUTPUT_FILE:
                    t.output_file = value
                elif attr == ATTR_SEGMENTS_COUNT:
                    t.segments = int(value or 0)
            elif kind == "MSG" and len(f) >= 4:
                scan.messages.append(f[3])
        except ValueError:
            continue
    scan.titles = [titles[k] for k in sorted(titles)]
    return scan


def pick_main_title(titles: list[Title]) -> Title | None:
    """Longest title; ties broken by size and chapter count."""
    if not titles:
        return None
    return max(titles, key=lambda t: (round(t.duration / 60), t.size_bytes, t.chapters))


def find_drive(drives: list[Drive], drive: str) -> Drive | None:
    """Map a Windows drive letter ("D:") to the MakeMKV drive entry."""
    wanted = drive.rstrip("\\/").upper()
    for d in drives:
        if d.device.rstrip("\\/").upper() == wanted:
            return d
    with_media = [d for d in drives if d.has_media]
    return with_media[0] if len(with_media) == 1 else None


def key_problem(messages) -> str | None:
    for msg in messages:
        if KEY_PROBLEM_RE.search(msg):
            return msg
    return None


# ----------------------------------------------------------------------
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_robot(makemkvcon: str, args: list[str], timeout: float = 900.0,
              should_cancel=lambda: False, on_line=None) -> list[str]:
    """Run makemkvcon in robot mode and return its output lines."""
    proc = subprocess.Popen([makemkvcon, "-r", *args], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace", creationflags=_NO_WINDOW)
    lines: list[str] = []
    start = time.monotonic()
    watchdog = threading.Timer(timeout, proc.kill)    # also covers a silent, hung process
    watchdog.daemon = True
    watchdog.start()
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line.rstrip("\r\n"))
            if on_line is not None:
                on_line(lines[-1])
            if should_cancel() or time.monotonic() - start > timeout:
                proc.kill()
                break
        proc.wait(timeout=30)
    finally:
        watchdog.cancel()
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        if proc.stdout is not None:
            proc.stdout.close()
    return lines


def list_drives(makemkvcon: str) -> list[Drive]:
    return parse_output(run_robot(makemkvcon, ["--cache=1", "info", "disc:9999"], 120)).drives


def scan_disc(makemkvcon: str, index: int, min_length_s: int = 0,
              should_cancel=lambda: False, on_line=None) -> DiscScan:
    args = ["--cache=1", "--progress=-same"]
    if min_length_s:
        args.append(f"--minlength={min_length_s}")
    return parse_output(run_robot(makemkvcon, args + ["info", f"disc:{index}"],
                                  should_cancel=should_cancel, on_line=on_line))


# ----------------------------------------------------------------------
# Registration key (Windows stores it in HKCU\Software\MakeMKV\app_Key)
def get_registered_key() -> str | None:
    if sys.platform != "win32":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\MakeMKV") as k:
            return str(winreg.QueryValueEx(k, "app_Key")[0])
    except OSError:
        return None


def set_registered_key(key: str) -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\MakeMKV") as k:
        winreg.SetValueEx(k, "app_Key", 0, winreg.REG_SZ, key.strip())
    return True


def fetch_beta_key(timeout: float = 20.0) -> str | None:
    """Read the current free beta key published on the official MakeMKV forum."""
    req = urllib.request.Request(BETA_KEY_URL, headers={"User-Agent": "AutoRipMachine"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https URL
        html = resp.read().decode("utf-8", "replace")
    m = re.search(r"<code>\s*(T-[A-Za-z0-9@_\-]{20,})\s*</code>", html)
    return m.group(1) if m else None


def refresh_beta_key() -> str:
    """Install the latest beta key unless a purchased (non beta) key is registered."""
    current = get_registered_key()
    if current and not current.startswith("T-"):
        return "Chiave MakeMKV registrata (licenza acquistata)."
    key = fetch_beta_key()
    if not key:
        return "Chiave beta non trovata sul forum MakeMKV."
    if key == current:
        return "Chiave beta MakeMKV già aggiornata."
    if set_registered_key(key):
        return "Chiave beta MakeMKV aggiornata."
    return f"Chiave beta: {key}"
