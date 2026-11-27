---
name: telegram-bot-builder
description: Maintain the Telegram Enterprise MCP with safe read and explicit-write Telegram Bot API tools.
---

# Workflow

1. Inspect the repository, `git status`, runtime, and existing tests before
   editing. Keep changes within the requested scope.
2. Testing is a hard gate: before every bot update, run the single offline E2E
   suite at `bots/nova_isr_music_bot/tests/test_e2e.py` and record the baseline
   result. After every update, rerun it and add coverage for changed behavior.
   Never place tests in runtime/data folders or at the repository root.
   After an authorized update, if the bot is already running, restart it
   gracefully from its bot directory so it reloads `.env`; never print or
   expose the token. Token rotation itself stays a manual BotFather action.
3. Never request or print `TELEGRAM_BOT_TOKEN`. Use local environment variables
   or a secret manager; do not commit `.env`, databases, media, or credentials.
   Keep generated previews and cached cover art under ignored bot data paths.
4. Preserve the default dry-run behavior, exact chat allowlist, explicit
   `execute=true` write gate, and separate refund enablement.
5. Use Telegram file IDs only. Do not add user-account scraping, arbitrary
   history access, remote transport, or automatic write retries.
6. For payment changes, retain XTR validation, server-side order identifiers,
   idempotency, successful-payment verification, and an auditable refund path.
   Do not claim live payment verification without evidence.
7. Add or update focused pytest coverage for validation, allowlisting, dry-run
   behavior, transport failures, and secret redaction. Run `python -m pytest -q`
   and report any unavailable dependencies or live checks.
8. Update the root README when runtime behavior, configuration, or safety
   limitations change. Do not deploy or push without explicit authorization.

## Preview-only music flow

For the NOVA music bot public experience:

1. On `/start` and `/music`, send every available static catalog-cover card in
   order; do not autoplay media or render a song-selection menu.
2. Put a centered play symbol on each card and expose a `▶️ Play 30s` callback.
   Send the generated 30-second MP4 preview only after an explicit click, with
   `supports_streaming=True` and `protect_content=True`.
   Send the full MP3 only after a validated Telegram Stars payment; stale or
   unauthenticated callbacks must never bypass payment.
3. Use exactly three short campaign lines per preview. Do not add automatic
   next/previous navigation to the preview message.
4. Provide reaction buttons with server-counted per-track totals. Toggle by
   `(user, track, reaction)` under the existing SQLite mutation lock; never
   accept client-supplied counts.
5. Cover catalog, preview-only, reaction, and presentation flows in the single
   offline E2E suite at `bots/nova_isr_music_bot/tests/test_e2e.py`; do not use
   live Telegram or real payments. Cover invoice creation, pre-checkout
   validation, payment idempotency, and download authorization offline.

## NOVA music catalog and Suno metadata

1. Treat `bots/nova_isr_music_bot/catalog.json` as display metadata for the
   local MP3 library. Keep titles normalized, descriptions concise, campaigns
   exactly three lines, and cover URLs optional.
   Apply full title case only at the presentation boundary; do not rename
   normalized MP3 filenames or storage keys for menu formatting.
2. Use Suno MCP only when the user explicitly requests metadata, analysis,
   artwork, upload, or generation. Do not assume a local MP3 upload will be
   accepted; Suno may reject audio for copyright reasons.
3. When an MP3 contains an original Suno clip ID, prefer retrieving metadata
   from that owned clip rather than repeatedly uploading the file. Record only
   non-secret identifiers, cover URLs, and descriptions in the catalog.
4. Keep fallback descriptions visibly grounded in embedded production tags or
   local inspection. Never label fallback text as Suno-generated metadata.
5. Catalog startup sync must be idempotent, use SHA-256 content identity, keep
   full files and previews inside the bot data directory, and tolerate one
   missing or failed cover without preventing other tracks from loading.
6. Cache cover images locally with bounded timeouts. Do not expose Suno cookies,
   signed upload URLs, API keys, or private session data in source, logs, or
   catalog files.
7. Validate `catalog.json`, compile Python, check shell syntax, and inspect the
   resulting SQLite track count and cover paths when changing catalog behavior.
8. Validate `bots/nova_isr_music_bot/logo.png` as a readable PNG for BotFather
   branding. Do not send it in `/start`; use each catalog track's cached Suno
   cover as the card visual and video thumbnail.

## Bulk local MP3 ingestion

When the user asks to upload or publish all local MP3 files into the NOVA bot:

1. Read the catalog and scan only the configured `mp3/nova_isr/` directory.
   Never recurse into `.env`, `.venv`, databases, caches, or unrelated media.
2. Start the bot or run its normal startup sync. The sync copies full tracks,
   generates midpoint previews with FFmpeg, and upserts rows by SHA-256 hash.
3. Confirm every catalog entry has a readable full file and preview. Confirm
   cover paths only when cover art was actually downloaded; missing cover art
   must not block the rest of the catalog.
4. Treat “uploaded to the bot” as local catalog publication unless Telegram
   message delivery was explicitly requested. A bot cannot impersonate the
   admin user to send incoming audio messages to itself.
5. For actual Telegram message uploads, require the configured private admin
   account to send the audio, then let the authenticated upload handler process
   it. Never bypass the private-admin authorization check.
6. Report exact counts for source files, indexed tracks, previews, and covers;
   do not claim Telegram delivery when only local indexing was performed.
7. Keep the tracked `logo.png` at the bot root for BotFather branding; do not
   copy it into ignored runtime data or send it as the bot's welcome message.
