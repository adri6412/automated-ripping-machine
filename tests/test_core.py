import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm.core import bluray, disc, makemkv  # noqa: E402
from arm.core.config import Config  # noqa: E402
from arm.core.disc import DiscType  # noqa: E402
from arm.core import processes  # noqa: E402
from tests import fixtures  # noqa: E402


class BlurayTests(unittest.TestCase):
    def test_title_and_uhd(self):
        with TemporaryDirectory() as a, TemporaryDirectory() as b:
            root = fixtures.make_bluray(Path(a))
            self.assertEqual(bluray.disc_title(root), "Test Movie")
            self.assertFalse(bluray.is_uhd(root))
            self.assertTrue(bluray.is_uhd(fixtures.make_bluray(Path(b), uhd=True)))


class MakeMKVTests(unittest.TestCase):
    def test_parse_fields_with_quotes_and_escapes(self):
        self.assertEqual(makemkv.parse_fields('1,2,"a, \\"b\\"",""'), ["1", "2", 'a, "b"', ""])
        self.assertEqual(makemkv.parse_line('TINFO:0,9,0,"1:40:00"'), ("TINFO", ["0", "9", "0", "1:40:00"]))
        self.assertIsNone(makemkv.parse_line("random text"))

    def test_parse_info(self):
        scan = makemkv.parse_output(fixtures.MAKEMKV_INFO.splitlines())
        self.assertEqual(scan.disc_type, "Blu-ray disc")
        self.assertEqual(scan.name, "Test Movie")
        self.assertEqual(len(scan.titles), 3)
        t0 = scan.titles[0]
        self.assertEqual((t0.duration, t0.chapters, t0.size_bytes, t0.source_file),
                         (6000.0, 24, 27166914560, "00800.mpls"))
        self.assertEqual(scan.main_title().id, 0)          # the 1:39:59 decoy is smaller
        self.assertEqual(len(scan.drives), 2)
        self.assertEqual(makemkv.find_drive(scan.drives, "d:").index, 0)
        self.assertEqual(makemkv.find_drive(scan.drives, "SIM:").index, 0)   # single disc fallback

    def test_key_problem(self):
        self.assertIsNone(makemkv.key_problem(["Operation successfully completed"]))
        self.assertTrue(makemkv.key_problem(["This application version is too old."]))

    def test_duration(self):
        self.assertEqual(makemkv.parse_duration("0:12:30"), 750)
        self.assertEqual(makemkv.parse_duration("bad"), 0)


class IdentifyTests(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.get("ARM_SIM_DRIVE")

    def tearDown(self):
        if self._env is None:
            os.environ.pop("ARM_SIM_DRIVE", None)
        else:
            os.environ["ARM_SIM_DRIVE"] = self._env

    def identify(self, root: Path):
        os.environ["ARM_SIM_DRIVE"] = str(root)
        return disc.identify("SIM:")

    def test_types(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            bd = fixtures.make_bluray(base / "BD")
            uhd = fixtures.make_bluray(base / "UHD", uhd=True)
            dv = fixtures.make_dvd(base / "MY_DVD")
            cd = base / "CD"
            cd.mkdir()
            (cd / ".audiocd").write_text("12")
            data = base / "DATA"
            data.mkdir()
            (data / "readme.txt").write_text("x")

            info = self.identify(bd)
            self.assertEqual(info.type, DiscType.BLURAY)
            self.assertEqual(info.title, "Test Movie")
            self.assertEqual(self.identify(uhd).type, DiscType.UHD_BLURAY)
            dvd_info = self.identify(dv)
            self.assertEqual(dvd_info.type, DiscType.DVD_VIDEO)
            self.assertEqual(dvd_info.title, "My Dvd")
            cd_info = self.identify(cd)
            self.assertEqual(cd_info.type, DiscType.AUDIO_CD)
            self.assertEqual(cd_info.audio_tracks, 12)
            self.assertEqual(self.identify(data).type, DiscType.DATA)


    def test_default_process(self):
        cfg = Config()
        info = disc.DiscInfo("D:", Path("."), DiscType.AUDIO_CD)
        cfg.cyanrip_path = sys.executable    # pretend the tool exists
        self.assertEqual(processes.default_process(info, cfg).id, "cd_flac")
        info.type = DiscType.UHD_BLURAY
        cfg.makemkvcon_path = sys.executable
        self.assertEqual(processes.default_process(info, cfg).id, "mkv_main")
        self.assertEqual([p.id for p in processes.processes_for(DiscType.DVD_VIDEO)],
                         ["mkv_main", "mkv_all"])          # MakeMKV backup is Blu-ray only

    def test_find_tool_in_installer_layout(self):
        from unittest import mock
        from arm.core import config
        exe = "makemkvcon64.exe" if sys.platform == "win32" else "makemkvcon64"
        with TemporaryDirectory() as tmp, mock.patch.object(config, "install_dir",
                                                          return_value=Path(tmp)), \
                mock.patch.object(config.shutil, "which", return_value=None), \
                mock.patch.dict(config._TOOL_HINTS, clear=True):
            nested = Path(tmp) / "tools" / "makemkv" / "MakeMKV"
            nested.mkdir(parents=True)
            (nested / exe).write_bytes(b"")
            self.assertEqual(config.find_tool("makemkvcon"), str(nested / exe))
            self.assertIsNone(config.find_tool("cyanrip"))

    def test_sanitize(self):
        self.assertEqual(disc.sanitize('A:B/C*D?'), "A_B_C_D_")
        self.assertEqual(disc.pretty_label("THE_MATRIX_D1"), "The Matrix D1")


if __name__ == "__main__":
    unittest.main()
