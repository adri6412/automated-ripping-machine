"""The full-screen pages of the state machine."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QListWidget,
                               QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout,
                               QWidget)

from .widgets import DiscWidget


def label(text: str = "", name: str = "body", wrap: bool = True, align=None) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    if align is not None:
        lbl.setAlignment(align)
    return lbl


def button(text: str, name: str = "", slot=None) -> QPushButton:
    btn = QPushButton(text)
    if name:
        btn.setObjectName(name)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if slot:
        btn.clicked.connect(slot)
    return btn


def card() -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    return frame


CENTER = Qt.AlignmentFlag.AlignCenter


# ----------------------------------------------------------------------
class IdlePage(QWidget):
    def __init__(self):
        super().__init__()
        root = QHBoxLayout(self)
        root.setContentsMargins(60, 40, 60, 40)
        root.setSpacing(50)

        left = QVBoxLayout()
        left.addStretch()
        self.disc = DiscWidget(300)
        left.addWidget(self.disc, 0, CENTER)
        left.addSpacing(30)
        self.title = label("Inserisci un disco", "h1", align=CENTER)
        left.addWidget(self.title)
        self.subtitle = label("Blu-ray, Blu-ray 4K, DVD Video e CD Audio vengono riconosciuti "
                              "automaticamente.", "muted", align=CENTER)
        left.addWidget(self.subtitle)
        left.addSpacing(20)
        self.tools_row = QHBoxLayout()
        self.tools_row.setSpacing(10)
        left.addLayout(self.tools_row)
        left.addStretch()
        root.addLayout(left, 3)

        right = card()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(24, 24, 24, 24)
        rl.addWidget(label("Ultimi rip", "h3"))
        self.history = QListWidget()
        self.history.setObjectName("history")
        self.history.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        rl.addWidget(self.history)
        right.setMinimumWidth(380)
        root.addWidget(right, 2)
        self._chips: list[QLabel] = []

    def set_tools(self, items: list[tuple[str, str]]) -> None:
        """items: (text, chip style name)"""
        while self.tools_row.count():
            item = self.tools_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._chips = []
        self.tools_row.addStretch()
        for text, style in items:
            chip = label(text, style, wrap=False)
            self.tools_row.addWidget(chip)
            self._chips.append(chip)
        self.tools_row.addStretch()

    def set_history(self, entries: list[dict]) -> None:
        self.history.clear()
        if not entries:
            self.history.addItem("Nessun rip ancora eseguito.")
            return
        for e in entries[:30]:
            mark = "✔" if e.get("ok") else "✘"
            self.history.addItem(f"{mark}  {e.get('when', '')}  ·  {e.get('type', '')}\n"
                                 f"    {e.get('title', '')} — {e.get('process', '')}")


# ----------------------------------------------------------------------
class WaitPage(QWidget):
    """Disc detected: identification and MakeMKV title scan."""
    retry = Signal()
    eject = Signal()

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(80, 40, 80, 60)
        lay.addStretch()
        self.disc = DiscWidget(260)
        lay.addWidget(self.disc, 0, CENTER)
        lay.addSpacing(24)
        self.type_badge = label("", "badge", wrap=False)
        lay.addWidget(self.type_badge, 0, CENTER)
        self.title = label("Lettura del disco…", "h1", align=CENTER)
        lay.addWidget(self.title)
        self.message = label("", "muted", align=CENTER)
        lay.addWidget(self.message)
        lay.addSpacing(20)
        self.bar = QProgressBar()
        self.bar.setObjectName("thin")
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        self.bar.setMaximumWidth(700)
        lay.addWidget(self.bar, 0, CENTER)
        self.elapsed = label("", "muted", align=CENTER)
        lay.addWidget(self.elapsed)
        lay.addSpacing(30)
        row = QHBoxLayout()
        row.addStretch()
        self.retry_btn = button("Riprova", "", self.retry.emit)
        self.eject_btn = button("⏏  Espelli", "danger", self.eject.emit)
        for b in (self.retry_btn, self.eject_btn):
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch()
        self.bar.setMinimumWidth(500)

    def set_mode(self, error: bool) -> None:
        self.retry_btn.setVisible(error)
        self.bar.setVisible(not error)
        self.disc.set_spinning(not error)


# ----------------------------------------------------------------------
class OptionCard(QFrame):
    """A large, selectable card describing one rip process."""
    clicked = Signal(object)

    def __init__(self, pid: str, title: str, desc: str, enabled: bool, recommended: bool):
        super().__init__()
        self.pid = pid
        self.setObjectName("option")
        self.setEnabled(enabled)
        self.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ForbiddenCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(6)
        head = QHBoxLayout()
        head.addWidget(label(title, "h3" if enabled else "optionDisabled", wrap=False))
        if recommended:
            head.addWidget(label("CONSIGLIATO", "badgeAccent", wrap=False))
        head.addStretch()
        lay.addLayout(head)
        lay.addWidget(label(desc, "muted" if enabled else "optionDisabled"))
        self.setProperty("enabled_", enabled)
        self._checked = False

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        self._checked = checked
        self.setProperty("checked", checked)
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event) -> None:
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self)
        super().mouseReleaseEvent(event)


# ----------------------------------------------------------------------
class ProposalPage(QWidget):
    start = Signal(str)          # process id
    eject = Signal()

    def __init__(self):
        super().__init__()
        root = QHBoxLayout(self)
        root.setContentsMargins(60, 40, 60, 40)
        root.setSpacing(40)

        left = QVBoxLayout()
        left.addStretch()
        self.disc = DiscWidget(240)
        left.addWidget(self.disc, 0, CENTER)
        left.addSpacing(20)
        self.type_badge = label("", "badge", wrap=False)
        left.addWidget(self.type_badge, 0, CENTER)
        self.title = label("", "h1", align=CENTER)
        left.addWidget(self.title)
        self.details = label("", "muted", align=CENTER)
        left.addWidget(self.details)
        left.addStretch()
        root.addLayout(left, 2)

        right = QVBoxLayout()
        right.addStretch()
        right.addWidget(label("Processo proposto", "h2"))
        right.addSpacing(10)
        self.options_box = QVBoxLayout()
        self.options_box.setSpacing(12)
        right.addLayout(self.options_box)
        right.addSpacing(10)
        self.hint = label("", "muted")
        right.addWidget(self.hint)
        right.addSpacing(16)
        row = QHBoxLayout()
        self.eject_btn = button("⏏  Espelli", "danger", self.eject.emit)
        row.addWidget(self.eject_btn)
        row.addStretch()
        self.start_btn = button("▶  Avvia", "primary", self._on_start)
        row.addWidget(self.start_btn)
        right.addLayout(row)
        right.addStretch()
        root.addLayout(right, 3)

        self._cards: list[OptionCard] = []

    def set_options(self, options: list[tuple[str, str, str, bool, bool]]) -> None:
        """options: (id, title, description, enabled, recommended)"""
        while self.options_box.count():
            item = self.options_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards = []
        for pid, title, desc, enabled, recommended in options:
            card_ = OptionCard(pid, title, desc, enabled, recommended)
            card_.setChecked(recommended and enabled)
            card_.clicked.connect(self._on_card_clicked)
            self.options_box.addWidget(card_)
            self._cards.append(card_)
        if not any(c.isChecked() for c in self._cards):
            first = next((c for c in self._cards if c.isEnabled()), None)
            if first:
                first.setChecked(True)
        self.start_btn.setEnabled(self.selected() is not None)

    def _on_card_clicked(self, card_: "OptionCard") -> None:
        for c in self._cards:
            c.setChecked(c is card_)
        self.start_btn.setEnabled(True)

    def selected(self) -> str | None:
        return next((c.pid for c in self._cards if c.isChecked()), None)

    def _on_start(self) -> None:
        pid = self.selected()
        if pid:
            self.start.emit(pid)


# ----------------------------------------------------------------------
class RunPage(QWidget):
    cancel = Signal()
    toggle_log = Signal(bool)

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(80, 40, 80, 40)
        top = QHBoxLayout()
        self.disc = DiscWidget(150)
        top.addWidget(self.disc)
        top.addSpacing(30)
        info = QVBoxLayout()
        info.addStretch()
        self.type_badge = label("", "badge", wrap=False)
        info.addWidget(self.type_badge, 0, Qt.AlignmentFlag.AlignLeft)
        self.title = label("", "h1")
        info.addWidget(self.title)
        self.process = label("", "h3")
        info.addWidget(self.process)
        info.addStretch()
        top.addLayout(info, 1)
        lay.addLayout(top)
        lay.addSpacing(30)
        self.percent = label("0%", "h1", wrap=False)
        self.percent.setStyleSheet("font-size: 64px; font-weight: 300;")
        lay.addWidget(self.percent)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(26)
        lay.addWidget(self.bar)
        lay.addSpacing(8)
        self.status = label("", "body")
        lay.addWidget(self.status)
        self.elapsed = label("", "muted")
        lay.addWidget(self.elapsed)
        lay.addSpacing(16)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        lay.addWidget(self.log, 1)
        self.spacer = QWidget()
        lay.addWidget(self.spacer, 1)
        row = QHBoxLayout()
        self.log_btn = button("Mostra log", "flat", self._toggle)
        row.addWidget(self.log_btn)
        row.addStretch()
        self.cancel_btn = button("■  Annulla", "danger", self.cancel.emit)
        row.addWidget(self.cancel_btn)
        lay.addLayout(row)
        self.set_log_visible(False)

    def _toggle(self) -> None:
        visible = not self.log.isVisible()
        self.set_log_visible(visible)
        self.toggle_log.emit(visible)

    def set_log_visible(self, visible: bool) -> None:
        self.log.setVisible(visible)
        self.spacer.setVisible(not visible)
        self.log_btn.setText("Nascondi log" if visible else "Mostra log")

    def set_progress(self, pct: float) -> None:
        if pct < 0:
            self.bar.setRange(0, 0)
            self.percent.setText("…")
        else:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(pct * 10))
            self.percent.setText(f"{pct:.1f}%")


# ----------------------------------------------------------------------
class DonePage(QWidget):
    dismiss = Signal()
    open_folder = Signal()
    eject = Signal()

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(80, 40, 80, 60)
        lay.addStretch()
        self.icon = label("✔", "bigIconOk", wrap=False, align=CENTER)
        lay.addWidget(self.icon)
        self.title = label("", "h1", align=CENTER)
        lay.addWidget(self.title)
        self.message = label("", "muted", align=CENTER)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.message)
        lay.addSpacing(10)
        self.hint = label("", "body", align=CENTER)
        lay.addWidget(self.hint)
        lay.addSpacing(30)
        row = QHBoxLayout()
        row.addStretch()
        self.open_btn = button("📂  Apri cartella", "", self.open_folder.emit)
        self.eject_btn = button("⏏  Espelli", "", self.eject.emit)
        self.ok_btn = button("OK", "primary", self.dismiss.emit)
        for b in (self.open_btn, self.eject_btn, self.ok_btn):
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch()

    def set_result(self, ok: bool, title: str, message: str, hint: str) -> None:
        self.icon.setText("✔" if ok else "✘")
        self.icon.setObjectName("bigIconOk" if ok else "bigIconErr")
        self.icon.style().unpolish(self.icon)
        self.icon.style().polish(self.icon)
        self.title.setText(title)
        self.message.setText(message)
        self.hint.setText(hint)
