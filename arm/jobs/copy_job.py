"""1:1 file copy of a (decrypted) disc with read retries and size verification."""
from __future__ import annotations

import os
import time
from pathlib import Path

from .base import JobCancelled, ThreadJob

CHUNK = 4 * 1024 * 1024
READ_RETRIES = 5


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def human_time(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class CopyJob(ThreadJob):
    title = "Copia 1:1 del disco"

    def __init__(self, source: Path, output_dir: Path, skip_names: tuple[str, ...] = ()):
        super().__init__(output_dir)
        self.source = Path(source)
        self.skip_names = {s.upper() for s in skip_names}

    def _files(self) -> list[tuple[Path, Path, int]]:
        items = []
        for dirpath, dirs, files in os.walk(self.source):
            dirs[:] = [d for d in dirs if d.upper() not in self.skip_names
                       and d not in ("System Volume Information", "$RECYCLE.BIN")]
            rel = Path(dirpath).relative_to(self.source)
            for name in files:
                if name.upper() in self.skip_names or name.startswith(".audiocd"):
                    continue
                src = Path(dirpath) / name
                try:
                    size = src.stat().st_size
                except OSError:
                    size = 0
                items.append((src, self.output_dir / rel / name, size))
        return items

    def _read_chunk(self, fh, offset: int, length: int, src: Path) -> bytes:
        last_error: OSError | None = None
        for attempt in range(READ_RETRIES):
            try:
                fh.seek(offset)
                return fh.read(length)
            except OSError as exc:
                last_error = exc
                self.log.emit(f"Errore di lettura {src.name} @ {offset} "
                              f"(tentativo {attempt + 1}/{READ_RETRIES}): {exc}")
                time.sleep(1 + attempt)
        raise OSError(f"Settore illeggibile in {src} a offset {offset}: {last_error}")

    def work(self) -> str:
        self.status.emit("Analisi dei file sul disco…")
        files = self._files()
        total = sum(size for _s, _d, size in files) or 1
        self.log.emit(f"{len(files)} file, {human_size(total)} da copiare in {self.output_dir}")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        done = 0
        t0 = time.monotonic()
        last_emit = 0.0
        for index, (src, dst, size) in enumerate(files, 1):
            dst.parent.mkdir(parents=True, exist_ok=True)
            self.log.emit(f"[{index}/{len(files)}] {src.relative_to(self.source)} ({human_size(size)})")
            written = 0
            with open(src, "rb", buffering=0) as fin, open(dst, "wb") as fout:
                while True:
                    if self.cancelled:
                        raise JobCancelled()
                    data = self._read_chunk(fin, written, CHUNK, src)
                    if not data:
                        break
                    fout.write(data)
                    written += len(data)
                    done += len(data)
                    now = time.monotonic()
                    if now - last_emit > 0.25:
                        last_emit = now
                        speed = done / max(0.001, now - t0)
                        eta = (total - done) / speed if speed > 0 else 0
                        self.progress.emit(100.0 * done / total)
                        self.status.emit(f"{src.name} — {human_size(done)} / {human_size(total)}"
                                         f" — {human_size(speed)}/s — restano {human_time(eta)}")
            if written != size:
                raise OSError(f"Dimensione errata per {src.name}: letti {written} di {size} byte")
            try:
                os.utime(dst, (src.stat().st_atime, src.stat().st_mtime))
            except OSError:
                pass
        self.progress.emit(100.0)
        return f"Copia completata ({human_size(total)}) in {self.output_dir}"
