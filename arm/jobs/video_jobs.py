"""Main-title remux jobs for Blu-ray (mkvmerge) and DVD (ffmpeg dvdvideo)."""
from __future__ import annotations

import re
from pathlib import Path

from .base import ProcessJob


class BlurayMkvJob(ProcessJob):
    """Remux a decrypted Blu-ray playlist (.mpls) to MKV with mkvmerge.

    mkvmerge reads the playlist, joins its clips and keeps chapters and
    track languages; no re-encoding happens (bit-exact streams).
    """
    title = "Blu-ray → MKV (film principale)"

    def __init__(self, mkvmerge: str, playlist: Path, output_file: Path, disc_title: str):
        super().__init__(output_file.parent)
        self.mkvmerge = mkvmerge
        self.playlist = playlist
        self.output_file = output_file
        self.disc_title = disc_title
        self._launched = False

    def next_command(self):
        if self._launched:
            return None
        self._launched = True
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.status.emit(f"Remux della playlist {self.playlist.name}…")
        return [self.mkvmerge, "--gui-mode", "-o", str(self.output_file),
                "--title", self.disc_title, str(self.playlist)]

    def parse_line(self, line: str) -> None:
        m = re.search(r"progress\s+(\d+)%", line, re.I)
        if m:
            self.progress.emit(float(m.group(1)))
            self.status.emit(f"Remux {self.playlist.name} → {self.output_file.name}: {m.group(1)}%")

    def on_command_finished(self, exit_code: int):
        # mkvmerge: 0 = ok, 1 = ok with warnings, 2 = error
        if exit_code in (0, 1) and self.output_file.is_file():
            return True
        self.output_file.unlink(missing_ok=True)
        return False

    def success_message(self) -> str:
        return f"File creato: {self.output_file}"


class DvdMkvJob(ProcessJob):
    """Remux a DVD title to MKV with ffmpeg's ``dvdvideo`` demuxer (ffmpeg ≥ 7)."""
    title = "DVD → MKV (film principale)"

    def __init__(self, ffmpeg: str, disc_root: Path, title_no: int, duration: float,
                 output_file: Path, disc_title: str):
        super().__init__(output_file.parent)
        self.ffmpeg = ffmpeg
        self.disc_root = disc_root
        self.title_no = title_no
        self.duration = max(1.0, duration)
        self.output_file = output_file
        self.disc_title = disc_title
        self._launched = False

    def next_command(self):
        if self._launched:
            return None
        self._launched = True
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.status.emit(f"Remux del titolo {self.title_no}…")
        return [self.ffmpeg, "-hide_banner", "-nostdin", "-y",
                "-f", "dvdvideo", "-title", str(self.title_no), "-i", str(self.disc_root),
                "-map", "0", "-c", "copy", "-metadata", f"title={self.disc_title}",
                "-progress", "pipe:1", "-nostats", str(self.output_file)]

    def parse_line(self, line: str) -> None:
        if line.startswith("out_time_us="):
            try:
                seconds = int(line.split("=", 1)[1]) / 1_000_000
            except ValueError:
                return
            pct = min(99.9, 100.0 * seconds / self.duration)
            self.progress.emit(pct)
            self.status.emit(f"Titolo {self.title_no} → {self.output_file.name}: {pct:.1f}%")

    def on_command_finished(self, exit_code: int):
        if exit_code == 0 and self.output_file.is_file():
            self.progress.emit(100.0)
            return True
        if any("dvdvideo" in line and ("Unknown input format" in line or "not found" in line)
               for line in self.output_lines):
            self.output_lines.append("Questa build di ffmpeg non supporta il demuxer dvdvideo: "
                                     "usa una build 'full' (≥ 7.0) con libdvdnav/libdvdread.")
        self.output_file.unlink(missing_ok=True)
        return False

    def success_message(self) -> str:
        return f"File creato: {self.output_file}"
