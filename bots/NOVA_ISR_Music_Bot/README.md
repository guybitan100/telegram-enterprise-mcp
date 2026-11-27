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

## Usage

Keep one polling instance running per token. Send `/admin` privately as the
configured admin, then send an MP3 as Telegram audio with its title in the
caption. The bot rejects duplicate files, creates a midpoint preview with
fade-in/out, and stores the original by SHA-256 content hash. Users browse the
catalog with `/start` or `/music`, preview tracks, purchase with Stars, and
download paid tracks again from **My purchases**.

Payment validation checks the order owner, currency, stored amount, pending
state, and track existence before accepting payment. Duplicate charges are
refunded. SQLite uses WAL mode and serialized order/payment mutations to reduce
concurrency errors.

Only publish tracks you may commercially distribute. Suno metadata and artwork
integration are not implemented; supply the title manually. Test Stars
payments and refunds before launch. No live Telegram test is claimed.

## Production gaps

Add durable checkout reconciliation, monitoring, admin review before
publication, pagination for large catalogs, automated backups, and a webhook
deployment before using this with real customers.
