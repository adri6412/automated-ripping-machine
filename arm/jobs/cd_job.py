"""Bit-perfect audio CD ripping with cyanrip.

cyanrip reads with cd-paranoia (re-reads until data is consistent), applies
the drive read offset, verifies every track against the AccurateRip
database and writes lossless FLAC (or WAV) plus a CUE sheet and a log with
checksums - the same guarantees as EAC secure mode.
"""
from __future__ import annotations

import re
import shlex
import time
from datetime import datetime
from pathlib import Path

from .base import ProcessJob


class CyanripJob(ProcessJob):
    title = "CD Audio → rip bit-perfect"

    def __init__(self, cyanrip: str, drive: str, music_dir: Path, *, fmt: str = "flac",
                 offset: int = 0, retries: int = 10, overread: bool = False,
                 musicbrainz: bool = True, extra_args: str = "", total_tracks: int = 0):
        super().__init__(Path(music_dir))
        self.cyanrip = cyanrip
        self.drive = drive
        self.fmt = fmt
        self.offset = offset
        self.retries = retries
        self.overread = overread
        self.extra_args = shlex.split(extra_args, posix=False) if extra_args else []
        self.total_tracks = max(1, total_tracks)
        # Metadata fallbacks: MusicBrainz → first release → no metadata
        self.attempts: list[list[str]] = [[]] if musicbrainz else []
        if musicbrainz:
            self.attempts.append(["-R", "1"])
        stamp = datetime.now().strftime("%Y-%m-%d %H.%M")
        self.attempts.append(["-N", "-a", f"album=CD Audio {stamp}:artist=Sconosciuto"])
        self.attempt = -1
        self.ripping_started = False
        self.current_track = 1
        self.result_dir: Path | None = None
        self._before: set[Path] = set()
        self.accurip_lines: list[str] = []

    # ------------------------------------------------------------------
    def base_command(self) -> list[str]:
        cmd = [self.cyanrip, "-d", self.drive, "-s", str(self.offset), "-r", str(self.retries),
               "-o", self.fmt, "-X"]
        if self.overread:
            cmd.append("-O")
        return cmd + self.extra_args

    def next_command(self):
        if self.result_dir is not None:
            return None
        self.attempt += 1
        if self.attempt >= len(self.attempts):
            raise RuntimeError("cyanrip non è riuscito a rippare il disco.")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._before = {p for p in self.output_dir.iterdir() if p.is_dir()}
        self._started = time.time()
        self.ripping_started = False
        extra = self.attempts[self.attempt]
        self.status.emit("Lettura TOC e ricerca metadati…" if "-N" not in extra
                         else "Rip senza metadati online…")
        return self.base_command() + extra

    def parse_line(self, line: str) -> None:
        low = line.lower()
        if "accurip" in low or "accuraterip" in low:
            self.accurip_lines.append(line.strip())
        m_track = re.search(r"track\s+(\d+)", line, re.I)
        m_pct = re.search(r"(\d{1,3}(?:\.\d+)?)%", line)
        if m_track and ("rip" in low or "encod" in low):
            self.current_track = int(m_track.group(1))
            self.ripping_started = True
        if m_pct and self.ripping_started:
            pct = float(m_pct.group(1))
            overall = ((self.current_track - 1) + pct / 100.0) / self.total_tracks * 100.0
            self.progress.emit(min(99.9, overall))
            self.status.emit(f"Traccia {self.current_track}/{self.total_tracks} — {pct:.1f}%")

    def _new_dir(self) -> Path | None:
        try:
            dirs = [p for p in self.output_dir.iterdir() if p.is_dir() and p not in self._before]
        except OSError:
            return None
        dirs = [d for d in dirs if d.stat().st_mtime >= self._started - 5]
        return max(dirs, key=lambda d: d.stat().st_mtime) if dirs else None

    def on_command_finished(self, exit_code: int):
        new_dir = self._new_dir()
        if exit_code == 0:
            self.result_dir = new_dir or self.output_dir
            self.progress.emit(100.0)
            return True
        if self.ripping_started:
            return False            # a real read failure: don't silently retry
        text = "\n".join(self.output_lines).lower()
        metadata_issue = any(k in text for k in ("musicbrainz", "release", "metadata", "-n", "-r"))
        if new_dir and not any(new_dir.iterdir()):
            new_dir.rmdir()
        if metadata_issue and self.attempt + 1 < len(self.attempts):
            self.log.emit("Metadati non disponibili, nuovo tentativo con opzioni di ripiego…")
            return None
        return False

    def success_message(self) -> str:
        summary = ""
        verified = [l for l in self.accurip_lines if "match" in l.lower() or "accurate" in l.lower()]
        if verified:
            summary = "\n" + "\n".join(verified[-3:])
        return f"Rip completato in {self.result_dir}{summary}"


class FindOffsetJob(ProcessJob):
    """Runs ``cyanrip -f`` to detect the drive read offset (needs a disc in AccurateRip)."""
    title = "Ricerca offset del lettore"

    def __init__(self, cyanrip: str, drive: str, work_dir: Path):
        super().__init__(work_dir)
        self.cyanrip = cyanrip
        self.drive = drive
        self._launched = False
        self.found_offset: int | None = None

    def next_command(self):
        if self._launched:
            return None
        self._launched = True
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return [self.cyanrip, "-d", self.drive, "-f"]

    def parse_line(self, line: str) -> None:
        m = re.search(r"offset[^\d+\-]*([+-]?\d+)", line, re.I)
        if m:
            self.found_offset = int(m.group(1))

    def success_message(self) -> str:
        if self.found_offset is None:
            return "Offset non determinato: controlla il log."
        return f"Offset rilevato: {self.found_offset:+d}"
