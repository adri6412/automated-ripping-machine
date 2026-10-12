"""Entry point."""
from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .core import winapi
from .core.config import Config
from .ui.main_window import MainWindow
from .ui.style import STYLESHEET


def main() -> int:
    winapi.suppress_error_dialogs()
    app = QApplication(sys.argv)
    app.setApplicationName("Automated Ripping Machine")
    app.setFont(QFont("Segoe UI", 11))
    app.setStyleSheet(STYLESHEET)
    cfg = Config.load()
    window = MainWindow(cfg)
    if cfg.fullscreen and "--windowed" not in sys.argv:
        window.showFullScreen()
    else:
        window.resize(1600, 900)
        window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
