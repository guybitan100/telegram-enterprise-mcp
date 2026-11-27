import json
import struct
import unittest
from pathlib import Path

from infra.presentation import display_title, id_from_callback


BOT_ROOT = Path(__file__).resolve().parents[1]


class BotSanityTests(unittest.TestCase):
    def test_catalog_is_valid_and_has_required_metadata(self):
        catalog = json.loads((BOT_ROOT / "catalog.json").read_text(encoding="utf-8"))

        self.assertGreater(len(catalog), 0)
        self.assertEqual(len({item["file"] for item in catalog}), len(catalog))
        for item in catalog:
            self.assertTrue(item["file"].endswith(".mp3"))
            self.assertTrue(item["title"])
            self.assertTrue(item["description"])

    def test_titles_are_presented_in_title_case(self):
        self.assertEqual(display_title("aatini turha sharrahni"), "Aatini Turha Sharrahni")
        self.assertEqual(display_title("girls, boys, everybody"), "Girls, Boys, Everybody")

    def test_callback_ids_are_strictly_parsed(self):
        self.assertEqual(id_from_callback("t:12", "t:"), 12)
        self.assertIsNone(id_from_callback("d:12", "t:"))
        self.assertIsNone(id_from_callback("t:not-a-number", "t:"))

    def test_logo_is_a_square_png(self):
        logo = (BOT_ROOT / "logo.png").read_bytes()
        self.assertEqual(logo[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", logo[16:24])
        self.assertEqual(width, height)
        self.assertGreater(width, 0)


if __name__ == "__main__":
    unittest.main()
