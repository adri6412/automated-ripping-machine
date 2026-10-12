"""Settings dialog (also full screen friendly)."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
                               QHBoxLayout, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from ..core import disc, makemkv
from ..core.config import Config, find_tool
from ..core.disc import DiscType
from ..core.processes import processes_for
from ..jobs.cd_job import FindOffsetJob
from .pages import button, label


class PathEdit(QWidget):
    def __init__(self, value: str, directory: bool, placeholder: str = ""):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(value)
        self.edit.setPlaceholderText(placeholder)
        lay.addWidget(self.edit, 1)
        browse = QPushButton("…")
        browse.setFixedWidth(60)
        browse.clicked.connect(self._browse)
        lay.addWidget(browse)
        self.directory = directory

    def _browse(self) -> None:
        if self.directory:
            path = QFileDialog.getExistingDirectory(self, "Seleziona cartella", self.edit.text())
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Seleziona eseguibile", self.edit.text(),
                                                  "Eseguibili (*.exe);;Tutti i file (*)")
        if path:
            self.edit.setText(path)

    def text(self) -> str:
        return self.edit.text().strip()


class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Impostazioni")
        self.resize(1100, 760)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 24, 30, 24)
        lay.addWidget(label("Impostazioni", "h2"))
        tabs = QTabWidget()
        lay.addWidget(tabs, 1)

        # --- General -----------------------------------------------------
        general = QWidget()
        f = QFormLayout(general)
        f.setSpacing(14)
        self.drive = QComboBox()
        self.drive.addItem("Automatico (primo lettore)", "")
        for d in disc.available_drives():
            self.drive.addItem(d, d)
        idx = self.drive.findData(cfg.drive)
        self.drive.setCurrentIndex(max(0, idx))
        f.addRow("Unità ottica", self.drive)
        self.video_dir = PathEdit(cfg.video_output_dir, True)
        self.music_dir = PathEdit(cfg.music_output_dir, True)
        self.data_dir = PathEdit(cfg.data_output_dir, True)
        f.addRow("Cartella film", self.video_dir)
        f.addRow("Cartella musica", self.music_dir)
        f.addRow("Cartella dischi dati", self.data_dir)
        self.eject = QCheckBox("Espelli il disco al termine")
        self.eject.setChecked(cfg.eject_when_done)
        f.addRow("", self.eject)
        self.fullscreen = QCheckBox("Avvia a schermo intero")
        self.fullscreen.setChecked(cfg.fullscreen)
        f.addRow("", self.fullscreen)
        tabs.addTab(general, "Generale")

        # --- Processes ---------------------------------------------------
        procs = QWidget()
        f = QFormLayout(procs)
        f.setSpacing(14)
        self.defaults: dict[str, QComboBox] = {}
        for attr, dtype in (("default_bluray", DiscType.BLURAY), ("default_uhd", DiscType.UHD_BLURAY),
                            ("default_dvd", DiscType.DVD_VIDEO), ("default_audio", DiscType.AUDIO_CD),
                            ("default_data", DiscType.DATA)):
            combo = QComboBox()
            for p in processes_for(dtype):
                combo.addItem(p.name, p.id)
            combo.setCurrentIndex(max(0, combo.findData(getattr(cfg, attr))))
            self.defaults[attr] = combo
            f.addRow(dtype.label, combo)
        tabs.addTab(procs, "Processi predefiniti")

        # --- MakeMKV -----------------------------------------------------
        mk = QWidget()
        f = QFormLayout(mk)
        f.setSpacing(14)
        f.addRow(label("MakeMKV legge e decifra DVD, Blu-ray e 4K UHD e li salva in MKV senza "
                       "perdita. Senza una licenza acquistata funziona con la chiave beta "
                       "gratuita pubblicata ogni mese sul forum ufficiale.", "muted"))
        key_row = QWidget()
        krl = QHBoxLayout(key_row)
        krl.setContentsMargins(0, 0, 0, 0)
        self.mk_key = QLineEdit(makemkv.get_registered_key() or "")
        self.mk_key.setPlaceholderText("T-… oppure la tua chiave di registrazione")
        krl.addWidget(self.mk_key, 1)
        krl.addWidget(button("Scarica chiave beta", "", self._fetch_beta_key))
        f.addRow("Chiave MakeMKV", key_row)
        self.mk_auto = QCheckBox("Aggiorna automaticamente la chiave beta all'avvio")
        self.mk_auto.setChecked(cfg.makemkv_auto_beta_key)
        f.addRow("", self.mk_auto)
        self.mk_min = QSpinBox()
        self.mk_min.setRange(0, 7200)
        self.mk_min.setSuffix(" s")
        self.mk_min.setValue(cfg.makemkv_min_title_s)
        f.addRow("Durata minima dei titoli", self.mk_min)
        self.mk_cache = QSpinBox()
        self.mk_cache.setRange(16, 4096)
        self.mk_cache.setSuffix(" MB")
        self.mk_cache.setValue(cfg.makemkv_cache_mb)
        f.addRow("Cache di lettura", self.mk_cache)
        tabs.addTab(mk, "MakeMKV")

        # --- Audio CD ----------------------------------------------------
        cd = QWidget()
        f = QFormLayout(cd)
        f.setSpacing(14)
        offset_row = QWidget()
        orl = QHBoxLayout(offset_row)
        orl.setContentsMargins(0, 0, 0, 0)
        self.offset = QSpinBox()
        self.offset.setRange(-3000, 3000)
        self.offset.setValue(cfg.cd_drive_offset)
        orl.addWidget(self.offset)
        self.find_offset_btn = button("Rileva offset (CD nel lettore)", "", self._find_offset)
        orl.addWidget(self.find_offset_btn)
        orl.addStretch()
        f.addRow("Offset di lettura (campioni)", offset_row)
        f.addRow(label("L'offset è indispensabile per un rip 1:1: cerca il tuo lettore su "
                       "accuraterip.com/driveoffsets.htm oppure usa «Rileva offset» con un CD "
                       "presente nel database AccurateRip.", "muted"))
        self.retries = QSpinBox()
        self.retries.setRange(1, 100)
        self.retries.setValue(cfg.cd_paranoia_retries)
        f.addRow("Tentativi per settore", self.retries)
        self.overread = QCheckBox("Overread lead-in/lead-out (solo se supportato dal lettore)")
        self.overread.setChecked(cfg.cd_overread)
        f.addRow("", self.overread)
        self.mb = QCheckBox("Metadati da MusicBrainz e copertina")
        self.mb.setChecked(cfg.cd_musicbrainz)
        f.addRow("", self.mb)
        self.cd_extra = QLineEdit(cfg.cd_extra_args)
        self.cd_extra.setPlaceholderText("es. -S 8")
        f.addRow("Argomenti extra cyanrip", self.cd_extra)
        self.offset_log = QPlainTextEdit()
        self.offset_log.setReadOnly(True)
        self.offset_log.setVisible(False)
        f.addRow(self.offset_log)
        tabs.addTab(cd, "CD Audio")

        # --- Tools -------------------------------------------------------
        tools = QWidget()
        f = QFormLayout(tools)
        f.setSpacing(14)
        self.tool_edits: dict[str, PathEdit] = {}
        for name, hint in (("cyanrip", "rip CD audio bit-perfect"),
                           ("makemkvcon", "MakeMKV: DVD / Blu-ray → MKV")):
            found = find_tool(name, getattr(cfg, f"{name}_path"))
            edit = PathEdit(getattr(cfg, f"{name}_path"), False,
                            f"auto: {found}" if found else "non trovato")
            self.tool_edits[name] = edit
            f.addRow(f"{name} ({hint})", edit)
        f.addRow(label("Lascia vuoto per la ricerca automatica (cartella tools\\ accanto al "
                       "programma, PATH, percorsi di installazione standard).", "muted"))
        tabs.addTab(tools, "Programmi")

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("Annulla", "", self.reject))
        row.addWidget(button("Salva", "primary", self._save))
        lay.addLayout(row)
        self._offset_job = None

    def _fetch_beta_key(self) -> None:
        try:
            key = makemkv.fetch_beta_key()
        except OSError as exc:
            QMessageBox.warning(self, "MakeMKV", f"Forum MakeMKV non raggiungibile: {exc}")
            return
        if not key:
            QMessageBox.warning(self, "MakeMKV", "Chiave beta non trovata sul forum MakeMKV.")
            return
        self.mk_key.setText(key)

    def _find_offset(self) -> None:
        cyan = find_tool("cyanrip", self.tool_edits["cyanrip"].text())
        drive = self.drive.currentData() or (disc.available_drives() or [None])[0]
        if not cyan or not drive:
            QMessageBox.warning(self, "Offset", "cyanrip o unità ottica non disponibili.")
            return
        from ..core.config import app_dir
        self.offset_log.setVisible(True)
        self.offset_log.clear()
        self.find_offset_btn.setEnabled(False)
        job = FindOffsetJob(cyan, drive, app_dir() / "offset")
        job.log.connect(self.offset_log.appendPlainText)
        job.finished.connect(self._offset_done)
        self._offset_job = job
        job.start()

    def _offset_done(self, ok: bool, message: str) -> None:
        self.find_offset_btn.setEnabled(True)
        job = self._offset_job
        if job and job.found_offset is not None:
            self.offset.setValue(job.found_offset)
        self.offset_log.appendPlainText(message)

    def _save(self) -> None:
        c = self.cfg
        c.drive = self.drive.currentData() or ""
        c.video_output_dir = self.video_dir.text()
        c.music_output_dir = self.music_dir.text()
        c.data_output_dir = self.data_dir.text()
        c.eject_when_done = self.eject.isChecked()
        c.fullscreen = self.fullscreen.isChecked()
        for attr, combo in self.defaults.items():
            setattr(c, attr, combo.currentData())
        c.makemkv_auto_beta_key = self.mk_auto.isChecked()
        c.makemkv_min_title_s = self.mk_min.value()
        c.makemkv_cache_mb = self.mk_cache.value()
        key = self.mk_key.text().strip()
        if key and key != (makemkv.get_registered_key() or ""):
            try:
                makemkv.set_registered_key(key)
            except OSError as exc:
                QMessageBox.warning(self, "MakeMKV", f"Impossibile salvare la chiave: {exc}")
        if self.offset.value() != c.cd_drive_offset:
            c.cd_offset_configured = True
        c.cd_drive_offset = self.offset.value()
        c.cd_paranoia_retries = self.retries.value()
        c.cd_overread = self.overread.isChecked()
        c.cd_musicbrainz = self.mb.isChecked()
        c.cd_extra_args = self.cd_extra.text()
        for name, edit in self.tool_edits.items():
            setattr(c, f"{name}_path", edit.text())
        c.save()
        self.accept()
