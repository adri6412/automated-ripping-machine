"""Background threads: drive polling and disc analysis / XReveal wait."""
from __future__ import annotations

import time

from PySide6.QtCore import QThread, Signal

from . import decryption, disc
from .config import Config
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
    """Identifies the disc, waits for XReveal to finish decrypting, analyses titles."""
    identified = Signal(object)                 # DiscInfo
    waiting = Signal(str, float)                # message, elapsed seconds
    ready = Signal(object)                      # DiscInfo
    timed_out = Signal(object, str)             # DiscInfo, last message
    failed = Signal(str)

    def __init__(self, drive: str, cfg: Config, skip_wait: bool = False):
        super().__init__()
        self.drive = drive
        self.cfg = cfg
        self.skip_wait = skip_wait
        self.cancelled = False
        self.force = False                      # "proceed anyway"

    def cancel(self) -> None:
        self.cancelled = True

    def _sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end and not (self.cancelled or self.force):
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

            if info.type.is_video and not self.skip_wait:
                start = time.monotonic()
                self.waiting.emit("Attendo che XReveal decifri il disco…", 0.0)
                self._sleep(self.cfg.xreveal_initial_delay_s)
                last = ""
                while not (self.cancelled or self.force):
                    result = decryption.check(info)
                    elapsed = time.monotonic() - start
                    last = result.message
                    if result.ready:
                        self.waiting.emit(f"Disco decifrato: {result.message}", elapsed)
                        break
                    if elapsed > self.cfg.xreveal_timeout_s:
                        self.timed_out.emit(info, last)
                        return
                    self.waiting.emit(f"Decifratura in corso… ({result.message})", elapsed)
                    self._sleep(self.cfg.xreveal_poll_interval_s)
                if self.cancelled:
                    return

            if info.type.is_video:
                self.waiting.emit("Analisi dei titoli…", 0.0)
                disc.analyze_video(info, self.cfg.min_main_title_minutes * 60)
                info.total_size = disc.dir_size(info.root) or info.total_size
            if not self.cancelled:
                self.ready.emit(info)
        except Exception as exc:  # noqa: BLE001 - reported to the UI
            self.failed.emit(f"Errore durante l'analisi del disco: {exc}")
