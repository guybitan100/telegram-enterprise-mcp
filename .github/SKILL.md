---
name: telegram-bot-builder
description: Maintain the Telegram Enterprise MCP with safe read and explicit-write Telegram Bot API tools.
---
# Workflow

1. Inspect the repository, `git status`, runtime, and existing tests before
   editing. Keep changes within the requested scope.
2. Never request or print `TELEGRAM_BOT_TOKEN`. Use local environment variables
   or a secret manager; do not commit `.env`, databases, media, or credentials.
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
