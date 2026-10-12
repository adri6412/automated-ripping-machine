"""Persistent JSON configuration."""
from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

APP_NAME = "AutoRipMachine"


def app_dir() -> Path:
    """Directory holding config, history and logs."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def install_dir() -> Path:
    """Directory of the program itself (works for PyInstaller builds too)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


@dataclass
class Config:
    # Drive selection: "" = first optical drive found
    drive: str = ""

    # Output folders
    video_output_dir: str = str(Path.home() / "Videos" / "Rips")
    music_output_dir: str = str(Path.home() / "Music" / "Rips")
    data_output_dir: str = str(Path.home() / "Documents" / "DiscBackups")

    # External tools (empty = auto-detect)
    cyanrip_path: str = ""
    makemkvcon_path: str = ""

    # MakeMKV (decrypts and rips DVD / Blu-ray / UHD)
    makemkv_auto_beta_key: bool = True     # keep the free beta key up to date
    makemkv_min_title_s: int = 120         # shorter titles are ignored (menus, trailers)
    makemkv_cache_mb: int = 1024

    # Default process per disc type (ids from arm.core.processes)
    default_bluray: str = "mkv_main"
    default_uhd: str = "mkv_main"
    default_dvd: str = "mkv_main"
    default_audio: str = "cd_flac"
    default_data: str = "data_copy"

    # Nothing starts on its own: rips begin only when the user presses "Avvia".
    eject_when_done: bool = False

    # Audio CD
    cd_drive_offset: int = 0
    cd_offset_configured: bool = False
    cd_paranoia_retries: int = 10
    cd_overread: bool = False
    cd_musicbrainz: bool = True
    cd_extra_args: str = ""

    # UI
    fullscreen: bool = True
    show_log: bool = False

    history: list = field(default_factory=list)

    # ------------------------------------------------------------------
    @classmethod
    def path(cls) -> Path:
        return app_dir() / "config.json"

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cfg
        names = {f.name for f in fields(cls)}
        for key, value in data.items():
            if key in names:
                setattr(cfg, key, value)
        return cfg

    def save(self) -> None:
        tmp = self.path().with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path())

    def add_history(self, entry: dict, keep: int = 50) -> None:
        self.history = ([entry] + list(self.history))[:keep]
        self.save()


# ----------------------------------------------------------------------
# Tool discovery
_TOOL_HINTS = {
    "cyanrip": [r"C:\Program Files\cyanrip\cyanrip.exe", r"C:\cyanrip\cyanrip.exe"],
    "makemkvcon": [r"C:\Program Files (x86)\MakeMKV\makemkvcon64.exe",
                   r"C:\Program Files\MakeMKV\makemkvcon64.exe",
                   r"C:\Program Files (x86)\MakeMKV\makemkvcon.exe",
                   r"C:\Program Files\MakeMKV\makemkvcon.exe"],
}
# Executable names to look for (MakeMKV ships a 64-bit "makemkvcon64").
_TOOL_NAMES = {"makemkvcon": ["makemkvcon64", "makemkvcon"]}


def find_tool(name: str, configured: str = "") -> str | None:
    """Locate an executable: explicit path, ./tools folder, PATH, usual locations."""
    if configured and Path(configured).is_file():
        return configured
    suffix = ".exe" if sys.platform == "win32" else ""
    tools = install_dir() / "tools"
    for base in _TOOL_NAMES.get(name, [name]):
        exe = base + suffix
        for candidate in (tools / exe, tools / name / exe):
            if candidate.is_file():
                return str(candidate)
        # Tools unpacked by the installer keep their archive layout
        # (e.g. tools/cyanrip/…/cyanrip.exe).
        if tools.is_dir():
            for candidate in sorted(tools.glob(f"*/**/{exe}")):
                if candidate.is_file():
                    return str(candidate)
        found = shutil.which(base)
        if found:
            return found
    for hint in _TOOL_HINTS.get(name, []):
        if Path(hint).is_file():
            return hint
    return None
