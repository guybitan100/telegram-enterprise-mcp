import asyncio
import json
import os
import sqlite3
import struct
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch


# The real handler module validates configuration at import time. Use harmless
# test-only values so this suite never reads or prints a developer's secrets.
os.environ["BOT_TOKEN"] = "123456789:offline-test-token"
os.environ["ADMIN_ID"] = "1"

from infra import bot as app


BOT_ROOT = Path(__file__).resolve().parents[1]


class FakeStartMessage:
    def __init__(self):
        self.from_user = SimpleNamespace(id=42)
        self.chat = SimpleNamespace(id=42, type="private")
        self.audios = []
        self.videos = []
        self.invoices = []
        self.text = None
        self.menu_reply_markup = None
        self.reply_markup = None

    async def answer_audio(self, audio, *, title, performer, caption, thumbnail, protect_content, reply_markup):
        self.audios.append(
            {
                "audio": audio,
                "caption": caption,
                "thumbnail": thumbnail,
                "protect_content": protect_content,
                "reply_markup": reply_markup,
            }
        )
        self.audio_title = title
        self.protect_content = protect_content
        self.reply_markup = reply_markup

    async def answer_video(self, video, *, duration, width, height, caption, thumbnail, supports_streaming, protect_content, reply_markup):
        self.videos.append(
            {
                "video": video,
                "duration": duration,
                "width": width,
                "height": height,
                "caption": caption,
                "thumbnail": thumbnail,
                "supports_streaming": supports_streaming,
                "protect_content": protect_content,
                "reply_markup": reply_markup,
            }
        )
        self.reply_markup = reply_markup

    async def answer_invoice(self, **kwargs):
        self.invoices.append(kwargs)
        return SimpleNamespace(message_id=1000 + len(self.invoices))

    async def answer(self, text, *, reply_markup=None):
        self.text = text
        self.menu_reply_markup = reply_markup
        self.reply_markup = reply_markup


class StartFlowE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.db.close()
        app.db = sqlite3.connect(":memory:")
        app.db.row_factory = sqlite3.Row
        app.db.execute(
            """
            CREATE TABLE tracks(
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                campaign TEXT NOT NULL DEFAULT '',
                cover TEXT,
                full TEXT NOT NULL,
                preview TEXT NOT NULL,
                preview_video TEXT,
                hash TEXT UNIQUE NOT NULL
            )
            """
        )
        app.db.execute(
            "CREATE TABLE reactions(uid INTEGER, track INTEGER, reaction TEXT, "
            "PRIMARY KEY(uid, track, reaction))"
        )
        app.db.execute(
            "CREATE TABLE orders(id TEXT PRIMARY KEY, uid INTEGER, track INTEGER, "
            "amount INTEGER, paid INTEGER DEFAULT 0, charge TEXT, "
            "invoice_message_id INTEGER)"
        )
        app.db.execute(
            "INSERT INTO tracks(title, description, full, preview, preview_video, hash) "
            "VALUES(?,?,?,?,?,?)",
            (
                "aatini turha sharrahni",
                "Offline test track",
                "/tmp/full.mp3",
                "/tmp/preview.mp3",
                "/tmp/preview.mp4",
                "offline-test-hash",
            ),
        )
        app.db.execute(
            "INSERT INTO tracks(title, description, full, preview, preview_video, hash) "
            "VALUES(?,?,?,?,?,?)",
            (
                "second preview",
                "Another offline test track",
                "/tmp/full-2.mp3",
                "/tmp/preview-2.mp3",
                "/tmp/preview-2.mp4",
                "offline-test-hash-2",
            ),
        )
        app.db.commit()

    @classmethod
    def tearDownClass(cls):
        app.db.close()

    def test_start_command_sends_all_song_previews_without_menu(self):
        message = FakeStartMessage()

        with patch("infra.bot.Path.is_file", return_value=True):
            asyncio.run(app.start(message))

        self.assertEqual(len(message.videos), 2)
        self.assertIn("NOVA ISR ∞ Music Store", message.text)
        self.assertTrue(all(item["protect_content"] for item in message.videos))
        self.assertTrue(all(item["supports_streaming"] for item in message.videos))
        self.assertTrue(all(item["duration"] == 30 for item in message.videos))
        download_buttons = [
            row[0].text
            for item in message.videos
            for row in item["reply_markup"].inline_keyboard[:1]
        ]
        self.assertEqual(download_buttons, ["⬇️ Buy full song • 50⭐"] * 2)
        self.assertFalse(message.audios)
        self.assertIsNone(message.menu_reply_markup)

    def test_download_button_creates_stars_invoice(self):
        class FakeQuery:
            def __init__(self):
                self.data = "b:1"
                self.from_user = SimpleNamespace(id=42)
                self.message = FakeStartMessage()

            async def answer(self, text=None, **kwargs):
                self.answer_text = text

        query = FakeQuery()
        with patch("infra.bot.Path.is_file", return_value=True):
            asyncio.run(app.buy(query))
            asyncio.run(app.buy(query))

        self.assertEqual(len(query.message.invoices), 1)
        invoice = query.message.invoices[0]
        self.assertEqual(invoice["currency"], "XTR")
        self.assertEqual(invoice["prices"][0].amount, 50)
        self.assertTrue(invoice["payload"])
        self.assertEqual(app.db.execute("SELECT count(*) FROM orders").fetchone()[0], 1)
        self.assertIsNotNone(
            app.db.execute("SELECT invoice_message_id FROM orders").fetchone()[0]
        )
        self.assertEqual(query.answer_text, "Payment invoice already sent above.")

    def test_reaction_toggles_and_updates_count(self):
        class FakeQueryMessage:
            def __init__(self):
                self.reply_markup = None

            async def edit_reply_markup(self, *, reply_markup):
                self.reply_markup = reply_markup

        class FakeQuery:
            def __init__(self):
                self.data = "react:1:heart"
                self.from_user = SimpleNamespace(id=42)
                self.message = FakeQueryMessage()
                self.answers = []

            async def answer(self, text=None, **kwargs):
                self.answers.append(text)

        query = FakeQuery()
        asyncio.run(app.react(query))
        self.assertEqual(app.db.execute("SELECT count(*) FROM reactions").fetchone()[0], 1)
        labels = [button.text for row in query.message.reply_markup.inline_keyboard for button in row]
        self.assertIn("❤️ ✓ 1", labels)

        asyncio.run(app.react(query))
        self.assertEqual(app.db.execute("SELECT count(*) FROM reactions").fetchone()[0], 0)

    def test_reaction_for_missing_track_is_rejected(self):
        class FakeQuery:
            data = "react:999:heart"
            from_user = SimpleNamespace(id=42)

            async def answer(self, text=None, **kwargs):
                self.answer_text = text

        query = FakeQuery()
        asyncio.run(app.react(query))
        self.assertEqual(query.answer_text, "Track unavailable.")
        self.assertEqual(app.db.execute("SELECT count(*) FROM reactions").fetchone()[0], 0)

    def test_catalog_campaigns_and_metadata_are_complete(self):
        catalog = json.loads((BOT_ROOT / "catalog.json").read_text(encoding="utf-8"))

        self.assertGreater(len(catalog), 0)
        self.assertEqual(len({item["file"] for item in catalog}), len(catalog))
        for item in catalog:
            self.assertTrue(item["file"].endswith(".mp3"))
            self.assertTrue(item["title"])
            self.assertTrue(item["description"])
            self.assertEqual(len(item["campaign"]), 3)
            self.assertTrue(all(line.strip() for line in item["campaign"]))

    def test_title_and_callback_presentation_helpers(self):
        self.assertEqual(app.display_title("aatini turha sharrahni"), "Aatini Turha Sharrahni")
        self.assertEqual(app.display_title("girls, boys, everybody"), "Girls, Boys, Everybody")
        self.assertEqual(app.id_from_callback("t:12", "t:"), 12)
        self.assertIsNone(app.id_from_callback("d:12", "t:"))
        self.assertIsNone(app.id_from_callback("t:not-a-number", "t:"))

    def test_logo_asset_is_a_square_png(self):
        logo = (BOT_ROOT / "logo.png").read_bytes()
        self.assertEqual(logo[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", logo[16:24])
        self.assertEqual(width, height)
        self.assertGreater(width, 0)


if __name__ == "__main__":
    unittest.main()
