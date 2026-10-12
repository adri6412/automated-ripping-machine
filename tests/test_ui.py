import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from tests import fixtures  # noqa: E402

APP = QApplication.instance() or QApplication([])


def wait_until(predicate, timeout_ms=15000) -> bool:
    loop = QEventLoop()
    timer = QTimer()
    timer.timeout.connect(lambda: predicate() and loop.quit())
    timer.start(50)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    timer.stop()
    return bool(predicate())


def process_events(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class ManualStartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self._env = {k: os.environ.get(k) for k in ("ARM_SIM_DRIVE", "XDG_CONFIG_HOME", "APPDATA")}
        os.environ["XDG_CONFIG_HOME"] = str(base / "cfg")
        os.environ["APPDATA"] = str(base / "cfg")
        os.environ["ARM_SIM_DRIVE"] = str(fixtures.make_bluray(base / "MOVIE"))
        self.out = base / "out"

    def tearDown(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def test_rip_starts_only_on_user_input(self):
        from arm.core.config import Config
        from arm.ui.main_window import MainWindow

        cfg = Config.load()
        cfg.video_output_dir = str(self.out)
        cfg.xreveal_initial_delay_s = 0
        window = MainWindow(cfg)
        try:
            self.assertTrue(wait_until(lambda: window.stack.currentWidget() is window.proposal))
            self.assertIsNotNone(window.proposal.selected())   # suggested, not started
            # Leave the proposal untouched: nothing may start by itself.
            process_events(3000)
            self.assertIs(window.stack.currentWidget(), window.proposal)
            self.assertIsNone(window.job)
            self.assertFalse(self.out.exists())

            # The user picks the 1:1 backup and presses "Avvia".
            backup = next(c for c in window.proposal._cards if c.pid == "bd_backup")
            window.proposal._on_card_clicked(backup)
            window.proposal.start_btn.click()
            self.assertTrue(wait_until(lambda: window.stack.currentWidget() is window.done))
            self.assertTrue(window.last_ok)
            self.assertTrue(any(self.out.rglob("*.m2ts")))
        finally:
            window.monitor.stop()
            window._stop_analyzer()
            window.deleteLater()


if __name__ == "__main__":
    unittest.main()
