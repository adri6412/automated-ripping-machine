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
    needs_decryption: bool = False


PROCESSES: list[Process] = [
    Process("bd_mkv_main", "Film principale → MKV",
            "Remux senza perdita della playlist principale (video, tutte le tracce audio, "
            "sottotitoli e capitoli) con mkvmerge.",
            (DiscType.BLURAY, DiscType.UHD_BLURAY), ("mkvmerge",), True),
    Process("bd_backup", "Backup completo 1:1",
            "Copia integrale e decifrata della struttura BDMV/CERTIFICATE: menu ed extra inclusi.",
            (DiscType.BLURAY, DiscType.UHD_BLURAY), (), True),
    Process("dvd_mkv_main", "Film principale → MKV",
            "Remux senza perdita del titolo principale con ffmpeg (dvdvideo): "
            "audio, sottotitoli e capitoli inclusi.",
            (DiscType.DVD_VIDEO,), ("ffmpeg",), True),
    Process("dvd_backup", "Backup completo 1:1",
            "Copia integrale e decifrata della cartella VIDEO_TS, menu inclusi.",
            (DiscType.DVD_VIDEO,), (), True),
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
    from ..jobs.video_jobs import BlurayMkvJob, DvdMkvJob

    name = info.safe_name
    video_dir = Path(cfg.video_output_dir)
    builders: dict[str, Callable[[], object]] = {}

    def bd_mkv():
        playlist = info.details.get("main_playlist")
        if not playlist:
            raise RuntimeError("Nessuna playlist principale trovata sul Blu-ray.")
        out = unique_path(video_dir / name / f"{name}.mkv")
        return BlurayMkvJob(tool_path("mkvmerge", cfg), Path(playlist), out, info.title or name)

    def dvd_mkv():
        title_no = info.details.get("main_title")
        if not title_no:
            raise RuntimeError("Nessun titolo principale trovato sul DVD.")
        out = unique_path(video_dir / name / f"{name}.mkv")
        return DvdMkvJob(tool_path("ffmpeg", cfg), info.root, int(title_no),
                         float(info.details.get("main_duration", 0)), out, info.title or name)

    def backup():
        return CopyJob(info.root, unique_path(video_dir / f"{name} [backup]"))

    def cd(fmt):
        return CyanripJob(tool_path("cyanrip", cfg), info.drive, Path(cfg.music_output_dir),
                          fmt=fmt, offset=cfg.cd_drive_offset, retries=cfg.cd_paranoia_retries,
                          overread=cfg.cd_overread, musicbrainz=cfg.cd_musicbrainz,
                          extra_args=cfg.cd_extra_args, total_tracks=info.audio_tracks)

    builders.update(
        bd_mkv_main=bd_mkv, bd_backup=backup, dvd_mkv_main=dvd_mkv, dvd_backup=backup,
        cd_flac=lambda: cd("flac"), cd_wav=lambda: cd("wav"),
        data_copy=lambda: CopyJob(info.root, unique_path(Path(cfg.data_output_dir) / name)),
    )
    return builders[proc.id]()
