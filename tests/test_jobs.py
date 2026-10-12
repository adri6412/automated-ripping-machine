import os
import stat
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from arm.jobs.cd_job import CyanripJob  # noqa: E402
from arm.jobs.copy_job import CopyJob  # noqa: E402
from arm.jobs.makemkv_job import MakeMKVJob  # noqa: E402
from tests import fixtures  # noqa: E402

APP = QApplication.instance() or QApplication([])


def run_job(job, timeout_ms=20000):
    result = {}
    loop = QEventLoop()
    progress = []
    job.progress.connect(progress.append)
    job.finished.connect(lambda ok, msg: (result.update(ok=ok, msg=msg), loop.quit()))
    QTimer.singleShot(timeout_ms, loop.quit)
    job.start()
    loop.exec()
    result["progress"] = progress
    return result


def fake_tool(directory: Path, name: str, body: str) -> str:
    path = directory / name
    path.write_text(f"#!{sys.executable}\nimport sys, os\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


@unittest.skipIf(sys.platform == "win32", "uses POSIX shebang fake tools")
class JobTests(unittest.TestCase):
    def test_copy_job(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dst:
            root = fixtures.make_bluray(Path(src))
            out = Path(dst) / "backup"
            res = run_job(CopyJob(root, out))
            self.assertTrue(res["ok"], res)
            for f in root.rglob("*"):
                if f.is_file():
                    copy = out / f.relative_to(root)
                    self.assertEqual(copy.read_bytes(), f.read_bytes())

    def test_cyanrip_fallback_to_no_metadata(self):
        script = r'''
args = sys.argv[1:]
if "-N" not in args:
    print("Unable to find release info on MusicBrainz for this CD, use -N to rip anyway")
    sys.exit(1)
assert args[args.index("-s") + 1] == "6"
album = args[args.index("-a") + 1].split(":")[0].split("=")[1]
os.makedirs(album, exist_ok=True)
for t in (1, 2):
    for p in (10.0, 55.5, 100.0):
        sys.stdout.write(f"\rRipping and encoding track {t}, progress - {p}%")
        sys.stdout.flush()
    print()
    open(os.path.join(album, f"0{t}.flac"), "w").write("x")
print("Track 1 accurately ripped (AccurateRip v2 match)")
'''
        with TemporaryDirectory() as tools, TemporaryDirectory() as music:
            exe = fake_tool(Path(tools), "cyanrip", script)
            job = CyanripJob(exe, "D:", Path(music), offset=6, total_tracks=2)
            res = run_job(job)
            self.assertTrue(res["ok"], res)
            self.assertEqual(job.attempt, 2)       # MB → -R 1 → -N
            self.assertTrue(job.result_dir and job.result_dir.name.startswith("CD Audio"))
            self.assertEqual(len(list(job.result_dir.glob("*.flac"))), 2)
            self.assertAlmostEqual(max(res["progress"]), 100.0)
            self.assertIn("AccurateRip", res["msg"])

    def test_cyanrip_read_error_is_not_retried(self):
        script = r'''
print("Ripping and encoding track 1, progress - 12.0%")
print("Error reading frame!")
sys.exit(1)
'''
        with TemporaryDirectory() as tools, TemporaryDirectory() as music:
            exe = fake_tool(Path(tools), "cyanrip", script)
            job = CyanripJob(exe, "D:", Path(music), total_tracks=5)
            res = run_job(job)
            self.assertFalse(res["ok"])
            self.assertEqual(job.attempt, 0)

    def test_makemkv_main_title_is_renamed(self):
        with TemporaryDirectory() as tools, TemporaryDirectory() as out:
            exe = fixtures.fake_makemkvcon(Path(tools))
            job = MakeMKVJob(exe, 0, Path(out) / "Movie", mode="title", title_id=0,
                             rename_to="Test Movie")
            logs = []
            job.log.connect(logs.append)
            res = run_job(job)
            self.assertTrue(res["ok"], res)
            self.assertEqual([p.name for p in job.result_files], ["Test Movie.mkv"])
            self.assertAlmostEqual(max(res["progress"]), 100.0)
            self.assertIn("Copy complete. 1 titles saved.", logs)
            self.assertFalse(any(line.startswith("PRGV") for line in logs))

    def test_makemkv_all_titles_and_backup(self):
        with TemporaryDirectory() as tools, TemporaryDirectory() as out:
            exe = fixtures.fake_makemkvcon(Path(tools))
            job = MakeMKVJob(exe, 0, Path(out) / "all", mode="all", min_length_s=120)
            self.assertTrue(run_job(job)["ok"])
            self.assertEqual(len(job.result_files), 3)
            backup = MakeMKVJob(exe, 0, Path(out) / "bk", mode="backup")
            self.assertTrue(run_job(backup)["ok"])
            self.assertTrue((Path(out) / "bk" / "BDMV" / "index.bdmv").is_file())

    def test_makemkv_expired_key_fails(self):
        script = r'''
print('MSG:5021,0,0,"This application version is too old. Please download the latest version.","x"')
sys.exit(0)
'''
        with TemporaryDirectory() as tools, TemporaryDirectory() as out:
            exe = fake_tool(Path(tools), "makemkvcon", script)
            res = run_job(MakeMKVJob(exe, 0, Path(out), mode="title", title_id=0))
            self.assertFalse(res["ok"])
            self.assertIn("chiave", res["msg"].lower())


if __name__ == "__main__":
    unittest.main()
