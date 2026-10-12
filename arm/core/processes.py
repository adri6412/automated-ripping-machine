"""Catalogue of rip processes and the logic that proposes the right one."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Config, find_tool
from .disc import DiscInfo, DiscType


@dataclass(frozen=True)
class Process:
    id: str
    name: str
    description: str
    disc_types: tuple[DiscType, ...]
    tools: tuple[str, ...] = ()


VIDEO = (DiscType.DVD_VIDEO, DiscType.BLURAY, DiscType.UHD_BLURAY)

PROCESSES: list[Process] = [
    Process("mkv_main", "Film principale → MKV",
            "MakeMKV decifra il disco e salva il titolo principale in MKV senza perdita: "
            "video, tutte le tracce audio, sottotitoli e capitoli.",
            VIDEO, ("makemkvcon",)),
    Process("mkv_all", "Tutti i titoli → MKV",
            "MakeMKV salva in MKV tutti i titoli più lunghi della durata minima "
            "(film, extra, episodi delle serie).",
            VIDEO, ("makemkvcon",)),
    Process("bd_backup", "Backup decifrato 1:1",
            "Copia integrale e decifrata del Blu-ray (BDMV, menu, extra) con MakeMKV.",
            (DiscType.BLURAY, DiscType.UHD_BLURAY), ("makemkvcon",)),
    Process("cd_flac", "Rip bit-perfect FLAC",
            "cyanrip in modalità sicura: cd-paranoia, correzione offset, verifica AccurateRip, "
            "FLAC lossless + CUE + log, metadati MusicBrainz e copertina.",
            (DiscType.AUDIO_CD,), ("cyanrip",)),
    Process("cd_wav", "Rip bit-perfect WAV",
            "Come sopra ma con file WAV non compressi + CUE + log.",
            (DiscType.AUDIO_CD,), ("cyanrip",)),
    Process("data_copy", "Copia dei file",
            "Copia di tutti i file del disco con verifica delle dimensioni.",
            (DiscType.DATA,), ()),
]

BY_ID = {p.id: p for p in PROCESSES}


def processes_for(disc_type: DiscType) -> list[Process]:
    return [p for p in PROCESSES if disc_type in p.disc_types]


def default_process(info: DiscInfo, cfg: Config) -> Process | None:
    preferred = {
        DiscType.BLURAY: cfg.default_bluray,
        DiscType.UHD_BLURAY: cfg.default_uhd,
        DiscType.DVD_VIDEO: cfg.default_dvd,
        DiscType.AUDIO_CD: cfg.default_audio,
        DiscType.DATA: cfg.default_data,
    }.get(info.type)
    candidates = processes_for(info.type)
    proc = BY_ID.get(preferred or "")
    if proc not in candidates:
        proc = candidates[0] if candidates else None
    # If the preferred process needs a missing tool, fall back to one that works.
    if proc and missing_tools(proc, cfg):
        usable = [p for p in candidates if not missing_tools(p, cfg)]
        proc = usable[0] if usable else proc
    return proc


def tool_path(name: str, cfg: Config) -> str | None:
    return find_tool(name, getattr(cfg, f"{name}_path", ""))


def missing_tools(proc: Process, cfg: Config) -> list[str]:
    return [t for t in proc.tools if not tool_path(t, cfg)]


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for i in range(2, 1000):
        candidate = path.with_name(f"{path.stem} ({i}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Impossibile trovare un nome libero per {path}")


def build_job(proc: Process, info: DiscInfo, cfg: Config):
    """Instantiate the Job implementing ``proc`` for ``info``."""
    from ..jobs.cd_job import CyanripJob
    from ..jobs.copy_job import CopyJob
    from ..jobs.makemkv_job import MakeMKVJob

    name = info.safe_name
    video_dir = Path(cfg.video_output_dir)

    def makemkv(mode: str):
        index = info.details.get("makemkv_index")
        if index is None:
            raise RuntimeError("MakeMKV non ha riconosciuto il disco: ripeti l'analisi.")
        title_id = info.details.get("main_title_id")
        if mode == "title" and title_id is None:
            raise RuntimeError("MakeMKV non ha trovato un titolo principale.")
        folder = name + (" [backup]" if mode == "backup" else "")
        return MakeMKVJob(tool_path("makemkvcon", cfg), int(index), unique_path(video_dir / folder),
                          mode=mode, title_id=title_id, min_length_s=cfg.makemkv_min_title_s,
                          rename_to=name, cache_mb=cfg.makemkv_cache_mb)

    def cd(fmt):
        return CyanripJob(tool_path("cyanrip", cfg), info.drive, Path(cfg.music_output_dir),
                          fmt=fmt, offset=cfg.cd_drive_offset, retries=cfg.cd_paranoia_retries,
                          overread=cfg.cd_overread, musicbrainz=cfg.cd_musicbrainz,
                          extra_args=cfg.cd_extra_args, total_tracks=info.audio_tracks)

    builders: dict[str, Callable[[], object]] = {
        "mkv_main": lambda: makemkv("title"),
        "mkv_all": lambda: makemkv("all"),
        "bd_backup": lambda: makemkv("backup"),
        "cd_flac": lambda: cd("flac"),
        "cd_wav": lambda: cd("wav"),
        "data_copy": lambda: CopyJob(info.root, unique_path(Path(cfg.data_output_dir) / name)),
    }
    return builders[proc.id]()
