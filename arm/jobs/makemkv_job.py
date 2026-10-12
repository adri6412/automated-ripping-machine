"""DVD / Blu-ray / UHD ripping with makemkvcon (MakeMKV decrypts the disc itself)."""
from __future__ import annotations

import re
import time
from pathlib import Path

from ..core import makemkv
from .base import ProcessJob

PROGRESS_MAX_DEFAULT = 65536


class MakeMKVJob(ProcessJob):
    """``makemkvcon mkv`` (one title or all) or ``makemkvcon backup --decrypt``."""

    def __init__(self, makemkvcon: str, disc_index: int, output_dir: Path, *, mode: str,
                 title_id: int | None = None, min_length_s: int = 0, rename_to: str = "",
                 cache_mb: int = 1024):
        super().__init__(output_dir)
        if mode not in ("title", "all", "backup"):
            raise ValueError(mode)
        self.makemkvcon = makemkvcon
        self.disc_index = disc_index
        self.mode = mode
        self.title_id = title_id
        self.min_length_s = min_length_s
        self.rename_to = rename_to
        self.cache_mb = cache_mb
        self.title = {"title": "MakeMKV → MKV (film principale)", "all": "MakeMKV → MKV (tutti i titoli)",
                      "backup": "MakeMKV → backup decifrato"}[mode]
        self._launched = False
        self._started = 0.0
        self.task = ""
        self.subtask = ""
        self.saved: int | None = None
        self.failed: int | None = None
        self.messages: list[str] = []
        self.result_files: list[Path] = []

    # ------------------------------------------------------------------
    def next_command(self):
        if self._launched:
            return None
        self._launched = True
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._started = time.time()
        source = f"disc:{self.disc_index}"
        cmd = [self.makemkvcon, "-r", "--progress=-same", f"--cache={self.cache_mb}"]
        if self.mode == "backup":
            return cmd + ["backup", "--decrypt", source, str(self.output_dir)]
        if self.mode == "all" and self.min_length_s:
            cmd.append(f"--minlength={self.min_length_s}")
        target = "all" if self.mode == "all" else str(self.title_id)
        self.status.emit("MakeMKV: apertura del disco…")
        return cmd + ["mkv", source, target, str(self.output_dir)]

    def format_log(self, line: str) -> str | None:
        parsed = makemkv.parse_line(line)
        if not parsed:
            return line
        kind, fields = parsed
        if kind == "MSG" and len(fields) >= 4:
            return fields[3]
        return None         # progress/info records are rendered by the progress bar

    def parse_line(self, line: str) -> None:
        parsed = makemkv.parse_line(line)
        if not parsed:
            return
        kind, f = parsed
        try:
            if kind == "PRGV" and len(f) >= 3:
                total, maximum = int(f[1]), int(f[2]) or PROGRESS_MAX_DEFAULT
                pct = min(100.0, 100.0 * total / maximum)
                self.progress.emit(pct)
                label = self.subtask or self.task or "Copia in corso"
                self.status.emit(f"{label} — {pct:.1f}%")
            elif kind == "PRGT" and len(f) >= 3:
                self.task = f[2]
            elif kind == "PRGC" and len(f) >= 3:
                self.subtask = f[2]
            elif kind == "MSG" and len(f) >= 4:
                text = f[3]
                self.messages.append(text)
                m = re.search(r"(\d+)\s+titles?\s+saved(?:\D+(\d+)\s+failed)?", text, re.I)
                if m:
                    self.saved = int(m.group(1))
                    self.failed = int(m.group(2) or 0)
        except ValueError:
            pass

    def _new_files(self) -> list[Path]:
        pattern = "*" if self.mode == "backup" else "*.mkv"
        return [p for p in self.output_dir.rglob(pattern)
                if p.is_file() and p.stat().st_mtime >= self._started - 5]

    def on_command_finished(self, exit_code: int):
        files = self._new_files()
        problem = makemkv.key_problem(self.messages)
        if problem:
            self.output_lines.append(f"Problema con la chiave di MakeMKV: {problem} — aggiorna la "
                                     "chiave in Impostazioni → MakeMKV.")
            return False
        if exit_code != 0 or not files or (self.failed or 0) > 0 or self.saved == 0:
            if self.failed:
                self.output_lines.append(f"{self.failed} titoli non salvati.")
            return False
        if self.mode == "title" and self.rename_to and len(files) == 1:
            target = files[0].with_name(f"{self.rename_to}.mkv")
            if not target.exists():
                files[0].rename(target)
                files = [target]
        self.result_files = files
        self.progress.emit(100.0)
        return True

    def failure_message(self, exit_code: int) -> str:
        tail = [m for m in self.output_lines[-50:] if not m.startswith(("PRGV", "PRGT", "PRGC"))]
        text = " | ".join(self.format_log(m) or "" for m in tail[-3:]).strip(" |")
        return f"MakeMKV non è riuscito a completare il rip (codice {exit_code}). {text}"

    def success_message(self) -> str:
        if self.mode == "backup":
            return f"Backup decifrato creato in {self.output_dir}"
        names = ", ".join(f.name for f in self.result_files[:5])
        more = f" e altri {len(self.result_files) - 5}" if len(self.result_files) > 5 else ""
        return f"{len(self.result_files)} file MKV in {self.output_dir}: {names}{more}"
