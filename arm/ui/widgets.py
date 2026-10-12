"""Custom widgets."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QConicalGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

DISC_COLORS = {
    "none": ("#3a4256", "#566079"),
    "audio_cd": ("#c9a227", "#ffe08a"),
    "dvd_video": ("#8a5cf6", "#c9b2ff"),
    "bluray": ("#2f7cf6", "#9cc4ff"),
    "uhd_bluray": ("#111111", "#e6c35c"),
    "data": ("#33c27f", "#a8f0cd"),
    "unknown": ("#6b7280", "#c4c9d4"),
}


class DiscWidget(QWidget):
    """A painted optical disc that spins while the machine is busy."""

    def __init__(self, size: int = 260, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0.0
        self._kind = "none"
        self._spinning = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._pulse = 0.0

    def set_kind(self, kind: str) -> None:
        self._kind = kind if kind in DISC_COLORS else "unknown"
        self.update()

    def set_spinning(self, spinning: bool) -> None:
        self._spinning = spinning
        if spinning:
            self._timer.start(16)
        else:
            self._timer.start(40)   # keep a slow "breathing" glow when idle

    def showEvent(self, event):
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start(40 if not self._spinning else 16)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def _tick(self) -> None:
        if self._spinning:
            self._angle = (self._angle + 6) % 360
        self._pulse = (self._pulse + 0.04) % (2 * math.pi)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        c = QPointF(self.width() / 2, self.height() / 2)
        r = side / 2 - 8
        base, shine = (QColor(x) for x in DISC_COLORS[self._kind])

        glow = QRadialGradient(c, r + 8)
        alpha = 40 + int(30 * (math.sin(self._pulse) + 1) / 2)
        g = QColor(shine)
        g.setAlpha(alpha)
        glow.setColorAt(0.85, g)
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, r + 8, r + 8)

        cone = QConicalGradient(c, -self._angle)
        stops = [(0.0, base), (0.12, shine), (0.25, base), (0.5, base.darker(130)),
                 (0.62, shine), (0.75, base), (1.0, base)]
        for pos, col in stops:
            cone.setColorAt(pos, col)
        p.setBrush(cone)
        p.drawEllipse(c, r, r)

        p.setPen(QPen(QColor(255, 255, 255, 25), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for k in (0.9, 0.75, 0.6, 0.45):
            p.drawEllipse(c, r * k, r * k)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#0f1218"))
        p.drawEllipse(c, r * 0.32, r * 0.32)
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawEllipse(c, r * 0.22, r * 0.22)
        p.setBrush(QColor("#0f1218"))
        p.drawEllipse(c, r * 0.1, r * 0.1)
        p.end()

    def sizeHint(self):
        return self.size()

