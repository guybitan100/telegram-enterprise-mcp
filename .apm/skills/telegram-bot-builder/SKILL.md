---
name: telegram-bot-builder
description: Maintain the Telegram Enterprise MCP with safe read and explicit-write Telegram Bot API tools.
---

# Workflow

1. Inspect the repository, `git status`, runtime, and existing tests before
   editing. Keep changes within the requested scope.
2. Never request or print `TELEGRAM_BOT_TOKEN`. Use local environment variables
   or a secret manager; do not commit `.env`, databases, media, or credentials.
   Keep generated previews and cached cover art under ignored bot data paths.
3. Preserve the default dry-run behavior, exact chat allowlist, explicit
   `execute=true` write gate, and separate refund enablement.
4. Use Telegram file IDs only. Do not add user-account scraping, arbitrary
   history access, remote transport, or automatic write retries.
5. For payment changes, retain XTR validation, server-side order identifiers,
   idempotency, successful-payment verification, and an auditable refund path.
   Do not claim live payment verification without evidence.
6. Add or update focused pytest coverage for validation, allowlisting, dry-run
   behavior, transport failures, and secret redaction. Run `python -m pytest -q`
   and report any unavailable dependencies or live checks.
7. Update the root README when runtime behavior, configuration, or safety
   limitations change. Do not deploy or push without explicit authorization.

## NOVA music catalog and Suno metadata

1. Treat `bots/nova_isr_music_bot/catalog.json` as display metadata for the
   local MP3 library. Keep titles normalized, descriptions concise, and cover
   URLs optional.
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
