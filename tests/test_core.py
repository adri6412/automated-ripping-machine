import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm.core import bluray, decryption, disc, dvd  # noqa: E402
from arm.core.config import Config  # noqa: E402
from arm.core.disc import DiscType  # noqa: E402
from arm.core import processes  # noqa: E402
from tests import fixtures  # noqa: E402


class BlurayTests(unittest.TestCase):
    def test_parse_mpls(self):
        duration, clips, chapters = bluray.parse_mpls(
            fixtures.make_mpls([("00010", 3600), ("00011", 2400)], chapters=24))
        self.assertAlmostEqual(duration, 6000, places=3)
        self.assertEqual(clips, ["00010", "00011"])
        self.assertEqual(chapters, 24)

    def test_main_playlist_skips_decoys(self):
        with TemporaryDirectory() as tmp:
            root = fixtures.make_bluray(Path(tmp))
            pls = bluray.scan_playlists(root)
            self.assertEqual(len(pls), 3)
            main = bluray.pick_main_playlist(pls, 20 * 60)
            self.assertEqual(main.name, "00800.mpls")
            self.assertEqual(bluray.disc_title(root), "Test Movie")
            self.assertFalse(bluray.is_uhd(root))

    def test_uhd(self):
        with TemporaryDirectory() as tmp:
            self.assertTrue(bluray.is_uhd(fixtures.make_bluray(Path(tmp), uhd=True)))


class DvdTests(unittest.TestCase):
    def test_titles(self):
        with TemporaryDirectory() as tmp:
            root = fixtures.make_dvd(Path(tmp))
            titles = dvd.scan_titles(root)
            self.assertEqual([t.number for t in titles], [1, 2, 3])
            self.assertEqual([round(t.duration) for t in titles], [120, 5700, 60])
            main = dvd.pick_main_title(titles)
            self.assertEqual(main.number, 2)
            self.assertEqual(main.chapters, 28)


class DecryptionTests(unittest.TestCase):
    def test_vob_sector(self):
        self.assertTrue(decryption.dvd_sector_scrambled(fixtures.vob_sector(True)))
        self.assertFalse(decryption.dvd_sector_scrambled(fixtures.vob_sector(False)))
        self.assertIsNone(decryption.dvd_sector_scrambled(b"\x00" * 2048))

    def test_ts_unit(self):
        self.assertTrue(decryption.ts_unit_clear(fixtures.ts_unit(False)))
        self.assertFalse(decryption.ts_unit_clear(fixtures.ts_unit(True)))

    def test_dvd_check(self):
        with TemporaryDirectory() as a, TemporaryDirectory() as b:
            self.assertTrue(decryption.check_dvd(fixtures.make_dvd(Path(a))).ready)
            self.assertFalse(decryption.check_dvd(fixtures.make_dvd(Path(b), scrambled=True)).ready)

    def test_bluray_check(self):
        with TemporaryDirectory() as a, TemporaryDirectory() as b:
            self.assertTrue(decryption.check_bluray(fixtures.make_bluray(Path(a))).ready)
            self.assertFalse(decryption.check_bluray(
                fixtures.make_bluray(Path(b), encrypted=True)).ready)


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

            disc.analyze_video(info, 20 * 60)
            self.assertTrue(info.details["main_playlist"].endswith("00800.mpls"))
            disc.analyze_video(dvd_info, 20 * 60)
            self.assertEqual(dvd_info.details["main_title"], 2)

    def test_default_process(self):
        cfg = Config()
        info = disc.DiscInfo("D:", Path("."), DiscType.AUDIO_CD)
        cfg.cyanrip_path = sys.executable    # pretend the tool exists
        self.assertEqual(processes.default_process(info, cfg).id, "cd_flac")
        info.type = DiscType.UHD_BLURAY
        self.assertEqual(processes.default_process(info, cfg).id, "bd_backup")

    def test_sanitize(self):
        self.assertEqual(disc.sanitize('A:B/C*D?'), "A_B_C_D_")
        self.assertEqual(disc.pretty_label("THE_MATRIX_D1"), "The Matrix D1")


if __name__ == "__main__":
    unittest.main()
