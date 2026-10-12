"""Main window and state machine: idle → detect/MakeMKV scan → proposal → rip → done."""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDateTime, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QMainWindow, QMessageBox, QStackedWidget,
                               QVBoxLayout, QWidget)

from ..core import makemkv, processes, winapi
from ..core.config import Config, app_dir
from ..core.disc import DiscInfo, DiscType
from ..core.monitor import DiscAnalyzer, DriveMonitor
from ..jobs.copy_job import human_size, human_time
from .pages import DonePage, IdlePage, ProposalPage, RunPage, WaitPage, button, label
from .settings_dialog import SettingsDialog


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600}h {seconds % 3600 // 60:02d}m" if seconds >= 3600 \
        else f"{seconds // 60}m {seconds % 60:02d}s"


class KeyRefresher(QThread):
    """Keeps the free MakeMKV beta key up to date (Windows registry)."""
    done = Signal(str, bool)

    def run(self) -> None:
        try:
            self.done.emit(makemkv.refresh_beta_key(), True)
        except Exception as exc:  # noqa: BLE001 - offline, forum down, ...
            self.done.emit(f"chiave non aggiornata ({exc.__class__.__name__})", False)


class MainWindow(QMainWindow):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("Automated Ripping Machine")
        self.drive: str | None = None
        self.info: DiscInfo | None = None
        self.analyzer: DiscAnalyzer | None = None
        self.job = None
        self.job_process = None
        self.job_started = 0.0
        self.result_path: Path | None = None
        self.log_file = None
        self.last_ok = False
        self.key_status = ""
        self.key_style = "chipOk"
        self.key_refresher: KeyRefresher | None = None
        self._old_threads: list = []

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.idle = IdlePage()
        self.wait = WaitPage()
        self.proposal = ProposalPage()
        self.run = RunPage()
        self.done = DonePage()
        for page in (self.idle, self.wait, self.proposal, self.run, self.done):
            self.stack.addWidget(page)

        self.wait.retry.connect(self._retry_detection)
        self.wait.eject.connect(self._eject)
        self.proposal.start.connect(self._start_process)
        self.proposal.eject.connect(self._eject)
        self.run.cancel.connect(self._cancel_job)
        self.run.toggle_log.connect(self._remember_log_pref)
        self.done.dismiss.connect(self._dismiss_result)
        self.done.open_folder.connect(self._open_result)
        self.done.eject.connect(self._eject)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._tick)
        self.clock_timer.start(1000)
        self.env_timer = QTimer(self)
        self.env_timer.timeout.connect(self._refresh_environment)
        self.env_timer.start(15000)

        QShortcut(QKeySequence("F11"), self, activated=self._toggle_fullscreen)
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.close)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self._open_settings)

        self.monitor = DriveMonitor(cfg)
        self.monitor.drives_changed.connect(self._on_drives)
        self.monitor.inserted.connect(self._on_inserted)
        self.monitor.removed.connect(self._on_removed)
        self.monitor.start()

        self._show_idle()
        self._refresh_environment()
        if cfg.makemkv_auto_beta_key and sys.platform == "win32":
            self.refresh_makemkv_key()
        self._tick()

    # ------------------------------------------------------------------ UI
    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("header")
        lay = QHBoxLayout(header)
        lay.setContentsMargins(30, 12, 20, 12)
        lay.addWidget(label("◉  AUTOMATED RIPPING MACHINE", "brand", wrap=False))
        lay.addSpacing(20)
        self.drive_chip = label("Ricerca lettore…", "chipWarn", wrap=False)
        lay.addWidget(self.drive_chip)
        self.makemkv_chip = label("MakeMKV", "chipWarn", wrap=False)
        lay.addWidget(self.makemkv_chip)
        lay.addStretch()
        self.clock = label("", "clock", wrap=False)
        lay.addWidget(self.clock)
        lay.addSpacing(10)
        self.settings_btn = button("⚙  Impostazioni", "flat", self._open_settings)
        lay.addWidget(self.settings_btn)
        lay.addWidget(button("⛶", "flat", self._toggle_fullscreen))
        lay.addWidget(button("⏻  Esci", "flat", self.close))
        return header

    def _set_chip(self, chip, text: str, style: str) -> None:
        chip.setText(text)
        chip.setObjectName(style)
        chip.style().unpolish(chip)
        chip.style().polish(chip)

    def _tick(self) -> None:
        self.clock.setText(QDateTime.currentDateTime().toString("ddd d MMM  HH:mm"))
        if self.job is not None and self.stack.currentWidget() is self.run:
            self.run.elapsed.setText(f"Tempo trascorso: {human_time(time.monotonic() - self.job_started)}")

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()

    def _remember_log_pref(self, visible: bool) -> None:
        self.cfg.show_log = visible
        self.cfg.save()

    # ----------------------------------------------------------- environment
    def _refresh_environment(self) -> None:
        if processes.tool_path("makemkvcon", self.cfg) is None:
            self._set_chip(self.makemkv_chip, "MakeMKV non trovato", "chipErr")
        elif self.key_status:
            self._set_chip(self.makemkv_chip, f"MakeMKV · {self.key_status}", self.key_style)
        else:
            self._set_chip(self.makemkv_chip, "MakeMKV pronto", "chipOk")
        chips = []
        for name, purpose in (("cyanrip", "CD audio"), ("makemkvcon", "DVD / Blu-ray")):
            ok = processes.tool_path(name, self.cfg) is not None
            chips.append((f"{'✔' if ok else '✘'} {name} · {purpose}", "chipOk" if ok else "chipErr"))
        if not self.cfg.cd_offset_configured:
            chips.append(("⚠ offset CD da configurare", "chipWarn"))
        self.idle.set_tools(chips)

    def refresh_makemkv_key(self) -> None:
        if self.key_refresher is not None and self.key_refresher.isRunning():
            return
        self.key_refresher = KeyRefresher()
        self.key_refresher.done.connect(self._on_key_refreshed)
        self.key_refresher.start()

    def _on_key_refreshed(self, message: str, ok: bool) -> None:
        self.key_status = "" if ok else message
        self.key_style = "chipOk" if ok else "chipWarn"
        self._refresh_environment()

    def _on_drives(self, drives: list) -> None:
        self.drive = self.monitor.current_drive()
        if self.drive:
            extra = f" (+{len(drives) - 1})" if len(drives) > 1 else ""
            self._set_chip(self.drive_chip, f"Lettore {self.drive}{extra}", "chipOk")
        else:
            self._set_chip(self.drive_chip, "Nessun lettore ottico", "chipErr")
            if self.stack.currentWidget() is self.idle:
                self.idle.title.setText("Nessun lettore ottico trovato")

    # ---------------------------------------------------------------- states
    def _show_idle(self) -> None:
        self.info = None
        self.idle.disc.set_kind("none")
        self.idle.disc.set_spinning(False)
        self.idle.title.setText("Inserisci un disco" if self.drive or self.monitor.current_drive()
                                else "Nessun lettore ottico trovato")
        self.idle.set_history(self.cfg.history)
        self.stack.setCurrentWidget(self.idle)

    def _busy(self) -> bool:
        return self.job is not None

    def _on_inserted(self, drive: str) -> None:
        if self._busy():
            return
        self.drive = drive
        self._start_analysis()

    def _on_removed(self, _drive: str) -> None:
        if self._busy():
            return
        self._stop_analyzer()
        if self.stack.currentWidget() in (self.wait, self.proposal):
            self._show_idle()

    def _start_analysis(self) -> None:
        self._stop_analyzer()
        self.wait.set_mode(error=False)
        self.wait.disc.set_kind("unknown")
        self.wait.type_badge.setText("Rilevamento…")
        self.wait.title.setText("Lettura del disco…")
        self.wait.message.setText(f"Unità {self.drive}")
        self.wait.elapsed.setText("")
        self.stack.setCurrentWidget(self.wait)
        an = DiscAnalyzer(self.drive, self.cfg)
        an.identified.connect(self._on_identified)
        an.waiting.connect(self._on_waiting)
        an.ready.connect(self._on_ready)
        an.failed.connect(self._on_analysis_failed)
        self.analyzer = an
        an.start()

    def _stop_analyzer(self) -> None:
        if self.analyzer is not None:
            self.analyzer.cancel()
            for sig in (self.analyzer.identified, self.analyzer.waiting, self.analyzer.ready,
                        self.analyzer.failed):
                try:
                    sig.disconnect()
                except (RuntimeError, TypeError):
                    pass
            if not self.analyzer.wait(3000):
                # Still blocked on a slow disc read: keep a reference until it exits.
                old = self.analyzer
                self._old_threads.append(old)
                old.finished.connect(lambda: self._old_threads.remove(old))
            self.analyzer = None

    def _on_identified(self, info: DiscInfo) -> None:
        self.info = info
        self.wait.disc.set_kind(info.type.value)
        self.wait.type_badge.setText(info.type.label)
        self.wait.title.setText(info.title or info.type.label)
        if info.type.is_video:
            self.wait.message.setText("Analisi dei titoli con MakeMKV (solo lettura, può richiedere "
                                      "fino a un paio di minuti)…")

    def _on_waiting(self, message: str, elapsed: float) -> None:
        self.wait.message.setText(message)
        if elapsed:
            self.wait.elapsed.setText(f"Analisi in corso da {human_time(elapsed)}")

    def _on_analysis_failed(self, message: str) -> None:
        self.wait.set_mode(error=True)
        self.wait.title.setText("Errore di lettura")
        self.wait.message.setText(message)
        self.wait.elapsed.setText("")

    def _retry_detection(self) -> None:
        self._start_analysis()

    # --------------------------------------------------------------- proposal
    def _on_ready(self, info: DiscInfo) -> None:
        self.info = info
        if info.type == DiscType.UNKNOWN:
            self.wait.set_mode(error=True)
            self.wait.title.setText("Disco non riconosciuto")
            self.wait.message.setText("Il disco è vuoto o illeggibile.")
            return
        p = self.proposal
        p.disc.set_kind(info.type.value)
        p.disc.set_spinning(False)
        p.type_badge.setText(info.type.label)
        p.title.setText(info.title or info.type.label)
        p.details.setText(self._describe(info))

        default = processes.default_process(info, self.cfg)
        options = []
        for proc in processes.processes_for(info.type):
            missing = processes.missing_tools(proc, self.cfg)
            desc = proc.description
            if missing:
                desc += f"\n⚠ Programma mancante: {', '.join(missing)}"
            enabled = not missing and self._process_possible(proc, info)
            options.append((proc.id, proc.name, desc, enabled, proc is default))
        p.set_options(options)
        self.stack.setCurrentWidget(p)
        # Never start on our own: the rip begins only when the user presses "Avvia".
        p.hint.setText("Scegli il processo e premi Avvia." if p.selected()
                       else "Nessun processo disponibile: controlla i programmi nelle impostazioni.")

    def _process_possible(self, proc, info: DiscInfo) -> bool:
        if proc.id in ("mkv_main", "mkv_all", "bd_backup"):
            return info.details.get("makemkv_index") is not None and (
                proc.id != "mkv_main" or info.details.get("main_title_id") is not None)
        return True

    def _describe(self, info: DiscInfo) -> str:
        lines = []
        if info.label and info.label != info.title:
            lines.append(f"Etichetta: {info.label}")
        if info.type == DiscType.AUDIO_CD:
            lines.append(f"{info.audio_tracks} tracce audio")
        if info.details.get("main_duration"):
            source = info.details.get("main_source")
            lines.append(f"Film principale: {fmt_duration(info.details['main_duration'])}, "
                         f"{info.details.get('main_chapters', 0)} capitoli"
                         + (f" ({source})" if source else ""))
        if info.details.get("main_size"):
            lines.append(f"Dimensione film: {human_size(info.details['main_size'])}")
        if info.details.get("titles"):
            lines.append(f"Titoli trovati da MakeMKV: {info.details['titles']}")
        if info.total_size:
            lines.append(f"Contenuto disco: {human_size(info.total_size)}")
        lines.append(f"Unità {info.drive}")
        return "\n".join(lines)

    # ----------------------------------------------------------------- running
    def _start_process(self, pid: str) -> None:
        info = self.info
        if info is None or self.job is not None:
            return
        proc = processes.BY_ID[pid]
        try:
            job = processes.build_job(proc, info, self.cfg)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Impossibile avviare", str(exc))
            return
        self.job = job
        self.job_process = proc
        self.job_started = time.monotonic()
        self.monitor.paused = True

        r = self.run
        r.disc.set_kind(info.type.value)
        r.disc.set_spinning(True)
        r.type_badge.setText(info.type.label)
        r.title.setText(info.title or info.type.label)
        r.process.setText(proc.name)
        r.status.setText("Avvio…")
        r.log.clear()
        r.set_progress(-1)
        r.set_log_visible(self.cfg.show_log)
        r.cancel_btn.setEnabled(True)
        self.stack.setCurrentWidget(r)

        logs = app_dir() / "logs"
        logs.mkdir(exist_ok=True)
        self.log_file = open(logs / f"{datetime.now():%Y%m%d-%H%M%S}-{pid}.log", "w",
                             encoding="utf-8")
        self.log_file.write(f"Disco: {info.type.label} — {info.title} ({info.label})\n"
                            f"Processo: {proc.name}\n\n")

        job.progress.connect(r.set_progress)
        job.status.connect(r.status.setText)
        job.log.connect(self._append_log)
        job.finished.connect(self._on_job_finished)
        job.start()

    def _append_log(self, line: str) -> None:
        self.run.log.appendPlainText(line)
        if self.log_file:
            self.log_file.write(line + "\n")
            self.log_file.flush()

    def _cancel_job(self) -> None:
        if self.job is None:
            return
        if QMessageBox.question(self, "Annullare?", "Vuoi davvero interrompere il rip in corso?") \
                == QMessageBox.StandardButton.Yes:
            self.run.cancel_btn.setEnabled(False)
            self.run.status.setText("Interruzione…")
            self.job.cancel()

    def _on_job_finished(self, ok: bool, message: str) -> None:
        job, proc, info = self.job, self.job_process, self.info
        self.job = None
        self.monitor.paused = False
        if self.log_file:
            self.log_file.write(f"\n{'OK' if ok else 'ERRORE'}: {message}\n")
            self.log_file.close()
            self.log_file = None
        self.run.disc.set_spinning(False)

        self.result_path = getattr(job, "result_dir", None) or getattr(job, "output_file", None) \
            or getattr(job, "output_dir", None)
        if self.result_path and Path(self.result_path).is_file():
            self.result_path = Path(self.result_path).parent
        elapsed = human_time(time.monotonic() - self.job_started)
        self.cfg.add_history({
            "when": datetime.now().strftime("%d/%m %H:%M"), "ok": ok,
            "type": info.type.label if info else "", "title": info.title if info else "",
            "process": proc.name if proc else "", "path": str(self.result_path or ""),
        })
        hint = f"Durata: {elapsed}"
        ejected = False
        if ok and self.cfg.eject_when_done and self.drive:
            ejected = winapi.eject(self.drive)
            if ejected:
                hint += " — disco espulso, inserisci il prossimo."
        self.done.set_result(ok, "Rip completato" if ok else "Rip non riuscito", message, hint)
        self.done.open_btn.setVisible(bool(self.result_path) and Path(self.result_path).exists())
        self.done.eject_btn.setVisible(not ejected)
        self.last_ok = ok
        self.stack.setCurrentWidget(self.done)

    def _dismiss_result(self) -> None:
        self._show_idle()
        if not self.last_ok:
            # Failed rip with the disc still inside: propose it again.
            self.monitor.rearm()

    def _open_result(self) -> None:
        if self.result_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result_path)))

    def _eject(self) -> None:
        self._stop_analyzer()
        if self.drive:
            winapi.eject(self.drive)
        if self.stack.currentWidget() is not self.done:
            self._show_idle()

    # ---------------------------------------------------------------- settings
    def _open_settings(self) -> None:
        if self._busy():
            QMessageBox.information(self, "Impostazioni", "Attendi la fine del rip in corso.")
            return
        dlg = SettingsDialog(self.cfg, self)
        if self.isFullScreen():
            dlg.setWindowState(Qt.WindowState.WindowMaximized)
        if dlg.exec():
            self._refresh_environment()
            self.monitor.rearm()

    def closeEvent(self, event) -> None:
        if self._busy():
            if QMessageBox.question(self, "Uscire?", "C'è un rip in corso. Interromperlo e uscire?") \
                    != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.job.cancel()
        elif QMessageBox.question(self, "Uscire?", "Chiudere Automated Ripping Machine?") \
                != QMessageBox.StandardButton.Yes:
            event.ignore()
            return
        self._stop_analyzer()
        self.monitor.stop()
        if self.key_refresher is not None:
            self.key_refresher.wait(3000)
        event.accept()
