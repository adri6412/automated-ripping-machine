"""Background threads: drive polling and disc analysis (MakeMKV title scan)."""
from __future__ import annotations

import time

from PySide6.QtCore import QThread, Signal

from . import disc, makemkv
from .config import Config, find_tool
from .disc import DiscInfo


class DriveMonitor(QThread):
    """Polls the optical drive and reports insert/remove transitions."""
    drives_changed = Signal(list)
    inserted = Signal(str)
    removed = Signal(str)

    def __init__(self, cfg: Config, interval: float = 1.5):
        super().__init__()
        self.cfg = cfg
        self.interval = interval
        self.paused = False
        self._stop = False
        self._drives: list[str] = []
        self._present: dict[str, bool] = {}

    def current_drive(self) -> str | None:
        if self.cfg.drive and self.cfg.drive in self._drives:
            return self.cfg.drive
        return self._drives[0] if self._drives else None

    def stop(self) -> None:
        self._stop = True
        self.wait(5000)

    def rearm(self) -> None:
        """Forget the current state so a disc already in the drive is reported again."""
        self._present.clear()

    def run(self) -> None:
        while not self._stop:
            drives = disc.available_drives()
            if drives != self._drives:
                self._drives = drives
                self.drives_changed.emit(drives)
            drive = self.current_drive()
            if drive and not self.paused:
                present = disc.media_present(drive)
                before = self._present.get(drive)
                self._present[drive] = present
                if present and not before:
                    self.inserted.emit(drive)
                elif before and not present:
                    self.removed.emit(drive)
            for _ in range(int(self.interval * 10)):
                if self._stop:
                    return
                time.sleep(0.1)


class DiscAnalyzer(QThread):
    """Identifies the disc and, for video discs, scans its titles with MakeMKV.

    Only reads the disc: nothing is ripped until the user presses "Avvia".
    """
    identified = Signal(object)                 # DiscInfo
    waiting = Signal(str, float)                # message, elapsed seconds
    ready = Signal(object)                      # DiscInfo
    failed = Signal(str)

    def __init__(self, drive: str, cfg: Config):
        super().__init__()
        self.drive = drive
        self.cfg = cfg
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def _sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end and not self.cancelled:
            time.sleep(0.1)

    def run(self) -> None:
        try:
            info: DiscInfo | None = None
            # The filesystem may need a few seconds to be mounted after spin-up.
            for _ in range(20):
                info = disc.identify(self.drive)
                if info.type != disc.DiscType.UNKNOWN or self.cancelled:
                    break
                self._sleep(1.5)
            if self.cancelled or info is None:
                return
            self.identified.emit(info)
            if info.type.is_video:
                self._scan_with_makemkv(info)
            if not self.cancelled:
                self.ready.emit(info)
        except Exception as exc:  # noqa: BLE001 - reported to the UI
            self.failed.emit(f"Errore durante l'analisi del disco: {exc}")

    def _scan_with_makemkv(self, info: DiscInfo) -> None:
        exe = find_tool("makemkvcon", self.cfg.makemkvcon_path)
        if not exe:
            return                              # the proposal shows the missing program
        start = time.monotonic()
        self.waiting.emit("MakeMKV: ricerca del lettore…", 0.0)
        drv = makemkv.find_drive(makemkv.list_drives(exe), self.drive)
        if drv is None:
            raise RuntimeError(f"MakeMKV non vede un disco nell'unità {self.drive}.")
        info.details["makemkv_index"] = drv.index
        state = {"task": "Analisi del disco con MakeMKV"}

        def on_line(line: str) -> None:
            parsed = makemkv.parse_line(line)
            if not parsed:
                return
            kind, f = parsed
            try:
                if kind in ("PRGT", "PRGC") and len(f) >= 3 and f[2]:
                    state["task"] = f[2]
                elif kind == "PRGV" and len(f) >= 3 and int(f[2]):
                    pct = 100.0 * int(f[1]) / int(f[2])
                    self.waiting.emit(f"{state['task']}… {pct:.0f}%", time.monotonic() - start)
                elif kind == "TCOUT":
                    self.waiting.emit(f"Trovati {f[0]} titoli, lettura dettagli…",
                                      time.monotonic() - start)
            except (ValueError, IndexError):
                pass

        scan = makemkv.scan_disc(exe, drv.index, self.cfg.makemkv_min_title_s,
                                 should_cancel=lambda: self.cancelled, on_line=on_line)
        if self.cancelled:
            return
        problem = makemkv.key_problem(scan.messages)
        if problem and not scan.titles:
            raise RuntimeError(f"{problem}\nAggiorna la chiave in Impostazioni → MakeMKV.")
        if not scan.titles:
            last = scan.messages[-1] if scan.messages else "nessun titolo trovato"
            raise RuntimeError(f"MakeMKV non è riuscito a leggere il disco: {last}")
        if scan.name and (not info.title or info.title == disc.pretty_label(info.label)):
            info.title = scan.name
        main = scan.main_title()
        info.details.update(titles=len(scan.titles), makemkv_titles=scan.titles)
        if main:
            info.details.update(main_title_id=main.id, main_duration=main.duration,
                                main_chapters=main.chapters, main_size=main.size_bytes,
                                main_source=main.source_file)
