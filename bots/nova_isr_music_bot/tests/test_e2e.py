import asyncio
import os
import sqlite3
import unittest
from types import SimpleNamespace


# The real handler module validates configuration at import time. Use harmless
# test-only values so this suite never reads or prints a developer's secrets.
os.environ["BOT_TOKEN"] = "123456789:offline-test-token"
os.environ["ADMIN_ID"] = "1"

from infra import bot as app


class FakeStartMessage:
    def __init__(self):
        self.from_user = SimpleNamespace(id=42)
        self.photo = None
        self.photo_caption = None
        self.audio = None
        self.audio_caption = None
        self.reply_markup = None

    async def answer_photo(self, photo, *, caption, reply_markup=None):
        self.photo = photo
        self.photo_caption = caption
        self.reply_markup = reply_markup

    async def answer_audio(self, audio, *, title, performer, caption, thumbnail, protect_content, reply_markup):
        self.audio = audio
        self.audio_caption = caption
        self.audio_title = title
        self.protect_content = protect_content
        self.reply_markup = reply_markup

    async def answer(self, text, *, reply_markup=None):
        self.audio_caption = text
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
                cover TEXT,
                full TEXT NOT NULL,
                preview TEXT NOT NULL,
                hash TEXT UNIQUE NOT NULL
            )
            """
        )
        app.db.execute(
            "CREATE TABLE reactions(uid INTEGER, track INTEGER, reaction TEXT, "
            "PRIMARY KEY(uid, track, reaction))"
        )
        app.db.execute(
            "INSERT INTO tracks(title, description, full, preview, hash) "
            "VALUES(?,?,?,?,?)",
            (
                "aatini turha sharrahni",
                "Offline test track",
                "/tmp/full.mp3",
                "/tmp/preview.mp3",
                "offline-test-hash",
            ),
        )
        app.db.execute(
            "INSERT INTO tracks(title, description, full, preview, hash) "
            "VALUES(?,?,?,?,?)",
            (
                "second preview",
                "Another offline test track",
                "/tmp/full-2.mp3",
                "/tmp/preview-2.mp3",
                "offline-test-hash-2",
            ),
        )
        app.db.commit()

    @classmethod
    def tearDownClass(cls):
        app.db.close()

    def test_start_command_builds_one_protected_preview_with_reactions(self):
        message = FakeStartMessage()

        asyncio.run(app.start(message))

        self.assertIsNotNone(message.photo)
        self.assertIn("NOVA ISR ∞ Music Store", message.photo_caption)
        self.assertIsNotNone(message.audio)
        self.assertTrue(message.protect_content)
        self.assertEqual(len(message.audio_caption.splitlines()), 3)
        labels = [button.text for row in message.reply_markup.inline_keyboard for button in row]
        self.assertIn("❤️ 0", labels)
        self.assertIn("Next ⏭", labels)
        self.assertNotIn("My purchases", labels)

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


if __name__ == "__main__":
    unittest.main()
