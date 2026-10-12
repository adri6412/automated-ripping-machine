"""Disc detection and classification."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from . import bluray, winapi


class DiscType(str, Enum):
    NONE = "none"
    AUDIO_CD = "audio_cd"
    DVD_VIDEO = "dvd_video"
    BLURAY = "bluray"
    UHD_BLURAY = "uhd_bluray"
    DATA = "data"
    UNKNOWN = "unknown"

    @property
    def label(self) -> str:
        return {
            DiscType.NONE: "Nessun disco",
            DiscType.AUDIO_CD: "CD Audio",
            DiscType.DVD_VIDEO: "DVD Video",
            DiscType.BLURAY: "Blu-ray",
            DiscType.UHD_BLURAY: "Blu-ray 4K UHD",
            DiscType.DATA: "Disco dati",
            DiscType.UNKNOWN: "Disco non riconosciuto",
        }[self]

    @property
    def is_video(self) -> bool:
        return self in (DiscType.DVD_VIDEO, DiscType.BLURAY, DiscType.UHD_BLURAY)


@dataclass
class DiscInfo:
    drive: str
    root: Path
    type: DiscType
    label: str = ""
    title: str = ""
    audio_tracks: int = 0
    total_size: int = 0
    details: dict = field(default_factory=dict)

    @property
    def safe_name(self) -> str:
        return sanitize(self.title or self.label or self.type.label)


def sanitize(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    name = re.sub(r"\s+", " ", name)
    return name[:120] or "Disco"


def pretty_label(label: str) -> str:
    """'THE_MATRIX_D1' -> 'The Matrix D1'."""
    if not label:
        return ""
    text = label.replace("_", " ").strip()
    if text.isupper():
        text = text.title()
    return text


def drive_root(drive: str) -> Path:
    sim = os.environ.get("ARM_SIM_DRIVE")
    if sim:
        return Path(sim)
    return Path(drive + "\\")


def available_drives() -> list[str]:
    if os.environ.get("ARM_SIM_DRIVE"):
        return ["SIM:"]
    return winapi.list_optical_drives()


def media_present(drive: str) -> bool:
    sim = os.environ.get("ARM_SIM_DRIVE")
    if sim:
        p = Path(sim)
        return p.is_dir() and any(p.iterdir())
    return winapi.media_present(drive)


def dir_size(root: Path) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def _find_ci(root: Path, *parts: str) -> Path | None:
    """Case-insensitive path lookup (discs are usually upper-case, ISO mounts vary)."""
    current = root
    for part in parts:
        try:
            match = next((c for c in current.iterdir() if c.name.upper() == part.upper()), None)
        except OSError:
            return None
        if match is None:
            return None
        current = match
    return current


def _sim_audio_tracks(root: Path) -> int:
    marker = root / ".audiocd"
    if marker.is_file():
        try:
            return int(marker.read_text().strip() or 10)
        except ValueError:
            return 10
    return 0


def identify(drive: str) -> DiscInfo:
    """Classify the disc currently in ``drive``.

    Detection only uses metadata that is readable without decryption
    (filesystem layout, TOC); MakeMKV takes care of the protected content.
    """
    root = drive_root(drive)
    label = winapi.volume_label(drive) if not os.environ.get("ARM_SIM_DRIVE") else root.name
    info = DiscInfo(drive, root, DiscType.UNKNOWN, label=label, title=pretty_label(label))

    # 1) TOC: audio tracks present?
    toc = winapi.read_toc(drive)
    audio_tracks = [t for t in toc if not t.is_data] if toc else []
    if os.environ.get("ARM_SIM_DRIVE"):
        audio_tracks = list(range(_sim_audio_tracks(root)))
    if not toc and not audio_tracks:
        # Windows exposes audio CDs through CDFS as TrackNN.cda files.
        try:
            cda = [p for p in root.iterdir() if p.suffix.lower() == ".cda"]
        except OSError:
            cda = []
        audio_tracks = cda

    # 2) Filesystem layout
    bdmv = _find_ci(root, "BDMV", "index.bdmv")
    video_ts = _find_ci(root, "VIDEO_TS", "VIDEO_TS.IFO")

    if bdmv:
        info.type = DiscType.UHD_BLURAY if bluray.is_uhd(root) else DiscType.BLURAY
        info.title = bluray.disc_title(root) or info.title
    elif video_ts:
        info.type = DiscType.DVD_VIDEO
    elif audio_tracks:
        info.type = DiscType.AUDIO_CD
        info.audio_tracks = len(audio_tracks)
        info.title = info.title if label and label.upper() != "AUDIO CD" else "CD Audio"
    else:
        try:
            has_files = any(root.iterdir())
        except OSError:
            has_files = False
        info.type = DiscType.DATA if has_files else DiscType.UNKNOWN

    if info.type in (DiscType.DATA, DiscType.DVD_VIDEO, DiscType.BLURAY, DiscType.UHD_BLURAY):
        info.total_size = dir_size(root)
    return info
