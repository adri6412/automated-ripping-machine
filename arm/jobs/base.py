"""Job infrastructure: every rip process is a :class:`Job` emitting Qt signals."""
from __future__ import annotations

import re
import time
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QThread, Signal


class JobCancelled(Exception):
    pass


class Job(QObject):
    progress = Signal(float)        # 0..100, or -1 for indeterminate
    status = Signal(str)            # short human readable state
    log = Signal(str)               # raw log lines
    finished = Signal(bool, str)    # success, message

    title = "Job"

    def __init__(self, output_dir: Path):
        super().__init__()
        self.output_dir = Path(output_dir)
        self.cancelled = False
        self.started_at = 0.0
        self._done = False

    def start(self) -> None:
        self.started_at = time.monotonic()
        self._run()

    def _run(self) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def cancel(self) -> None:
        self.cancelled = True

    def _finish(self, ok: bool, message: str) -> None:
        if self._done:
            return
        self._done = True
        self.finished.emit(ok, message)


# ----------------------------------------------------------------------
class _ThreadWorker(QThread):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.error: BaseException | None = None
        self.result = None

    def run(self) -> None:
        try:
            self.result = self.fn()
        except BaseException as exc:  # noqa: BLE001 - reported to the UI
            self.error = exc


class ThreadJob(Job):
    """Job whose body is a blocking Python function run in a QThread.

    The body may emit ``progress``/``status``/``log`` (Qt queues them across
    threads) and must periodically check ``self.cancelled``.
    """

    def _run(self) -> None:
        self._worker = _ThreadWorker(self.work)
        self._worker.finished.connect(self._on_thread_done)
        self._worker.start()

    def work(self) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    def _on_thread_done(self) -> None:
        err = self._worker.error
        if err is None:
            self._finish(True, self._worker.result or "Completato")
        elif isinstance(err, JobCancelled):
            self._finish(False, "Annullato dall'utente")
        else:
            self.log.emit(f"ERRORE: {err!r}")
            self._finish(False, str(err) or err.__class__.__name__)


# ----------------------------------------------------------------------
_PCT_RE = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s?%")


class ProcessJob(Job):
    """Runs one or more external commands sequentially through QProcess."""

    def __init__(self, output_dir: Path):
        super().__init__(output_dir)
        self.proc: QProcess | None = None
        self._buffer = ""
        self.output_lines: list[str] = []

    # Subclasses override -------------------------------------------------
    def next_command(self) -> list[str] | None:
        """Return the next command to run, or None when everything is done."""
        raise NotImplementedError

    def on_command_finished(self, exit_code: int) -> bool | None:
        """Return True to continue with next_command, False to fail, None to retry/next."""
        return exit_code == 0

    def parse_line(self, line: str) -> None:
        m = _PCT_RE.findall(line)
        if m:
            try:
                self.progress.emit(min(100.0, float(m[-1].replace(",", "."))))
            except ValueError:
                pass

    def format_log(self, line: str) -> str | None:
        """Text shown in the log for an output line (None hides it)."""
        return line

    def success_message(self) -> str:
        return f"Completato: {self.output_dir}"

    def failure_message(self, exit_code: int) -> str:
        tail = " | ".join(line for line in self.output_lines[-3:] if line)
        return f"Il processo è terminato con codice {exit_code}. {tail}"

    # Machinery -----------------------------------------------------------
    def _run(self) -> None:
        self._launch_next()

    def _launch_next(self) -> None:
        if self.cancelled:
            self._finish(False, "Annullato dall'utente")
            return
        try:
            cmd = self.next_command()
        except Exception as exc:  # noqa: BLE001
            self._finish(False, str(exc))
            return
        if cmd is None:
            self._finish(True, self.success_message())
            return
        self.output_lines = []
        self._buffer = ""
        self.log.emit("> " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.setWorkingDirectory(str(self.output_dir))
        self.proc.readyReadStandardOutput.connect(self._on_output)
        self.proc.finished.connect(self._on_finished)
        self.proc.errorOccurred.connect(self._on_error)
        self.proc.start(cmd[0], cmd[1:])

    def _on_output(self) -> None:
        data = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        self._buffer += data
        parts = re.split(r"[\r\n]", self._buffer)
        self._buffer = parts.pop()
        for line in parts:
            line = line.rstrip()
            if not line:
                continue
            self.output_lines.append(line)
            if len(self.output_lines) > 2000:
                del self.output_lines[:1000]
            self._emit_log(line)
            self.parse_line(line)

    def _emit_log(self, line: str) -> None:
        text = self.format_log(line)
        if text:
            self.log.emit(text)

    def _on_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._finish(False, f"Impossibile avviare {self.proc.program()}: verifica il percorso"
                                " nelle impostazioni.")

    def _on_finished(self, exit_code: int, _status) -> None:
        if self._buffer.strip():
            self.output_lines.append(self._buffer.strip())
            self._emit_log(self._buffer.strip())
            self.parse_line(self._buffer.strip())
            self._buffer = ""
        if self._done:
            return
        if self.cancelled:
            self._finish(False, "Annullato dall'utente")
            return
        verdict = self.on_command_finished(exit_code)
        if verdict is False:
            self._finish(False, self.failure_message(exit_code))
        else:
            self._launch_next()

    def cancel(self) -> None:
        super().cancel()
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            self.proc.kill()
