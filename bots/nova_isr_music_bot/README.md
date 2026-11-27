# NOVA ISR Music Store

Local polling bot for selling rights-cleared MP3 files with Telegram Stars.
Install Python 3.11+ and FFmpeg (`brew install ffmpeg`), then run `bash
setup.sh`. The script creates a private virtual environment and prompts for the
token and numeric admin ID without writing either value to shell history.

## Configuration

Required in `.env`:

```dotenv
BOT_TOKEN=replace-locally
ADMIN_ID=123456789
```

Optional settings:

```dotenv
BOT_USERNAME=NovaISRMusicBot
SUPPORT_HANDLE=guybit5
PRICE_STARS=50
PREVIEW_SECONDS=30
MAX_UPLOAD_MIB=19
LOG_LEVEL=INFO
```

The bot loads `.env` relative to `bot.py`, so it can be launched from any
working directory. Never commit `.env`, `data/store.db`, or media files.

## Layout

- `bot.py`: minimal launcher kept at the bot root for setup compatibility.
- `infra/bot.py`: public Telegram handlers, catalog, delivery, and payment flow.
- `infra/auth.py`: private admin authorization checks.
- `infra/config.py`: environment loading and validated runtime configuration.
- `catalog.json`: local MP3 titles, descriptions, three-line campaigns, and
  Suno cover metadata.
- `logo.png`: canonical BotFather profile icon; it is not sent inside the bot.
- `tests/`: focused bot tests; keep bot tests in this directory.
- `data/covers/`: downloaded cover art and generated previews; ignored by Git.

## Usage

Keep one polling instance running per token. Send `/admin` privately as the
configured admin, then send an MP3 as Telegram audio with its title in the
caption. The bot rejects duplicate files, creates a midpoint preview with
fade-in/out, and stores the original by SHA-256 content hash. The `/start` and
`/music` commands send all catalog tracks automatically as Telegram paid-media
videos with their Suno covers, without a song-selection menu. Telegram displays
the media as locked preview content with an `Unlock` button and opens the native
Stars payment screen in place. After payment, Telegram reveals the full
video/audio track in the same paid-media message. Each post contains three
short campaign lines and reaction buttons with per-track counters. A legacy
invoice/download path remains available for older preview messages and
purchased-track downloads.

At startup, the bot indexes MP3s from `mp3/nova_isr/`, generates 30-second
fallback previews, and generates full paid-media MP4 files from each MP3 and
cover. Suno cover art is cached locally and used as each video's thumbnail.
FFmpeg creates the video-player files in the ignored data directory.
Tracks rejected by Suno's
copyright filter keep their local production-tag descriptions and do not claim
Suno-generated cover metadata.

Before changing bot code or behavior, run the focused tests under `tests/` and
record the baseline. Rerun them after the change. Tests must not require `.env`,
live Telegram access, customer media, or the local runtime database.

Run the single offline end-to-end suite with:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

## Bot icon

Set the Telegram profile icon manually in **@BotFather**:

1. Send `/setuserpic`.
2. Select `@NovaISRMusicBot`.
3. Upload `logo.png` from this directory.

Telegram does not provide a supported Bot API method for changing a bot's
profile photo at runtime. Keep the BotFather icon and the tracked
`logo.png` synchronized when branding changes.

SQLite uses WAL mode and serialized mutations for reaction and catalog state.
Telegram Stars purchases use `XTR`, server-side order IDs, pre-checkout
validation, idempotent payment recording, and authorized full-track delivery.

Only publish tracks you may commercially distribute. Use Telegram's test
environment or a controlled purchase before launch; this repository's tests do
not perform live payments.

## Production gaps

Add durable checkout reconciliation, monitoring, admin review before
publication, pagination for large catalogs, automated backups, and a webhook
deployment before using this with real customers.
