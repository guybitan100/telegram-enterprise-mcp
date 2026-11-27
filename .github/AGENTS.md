# Repository instructions

Read `.github/SKILL.md` before changing the Telegram MCP. The repository-specific
agent guidance is in `.github/telegram-engineer.agent.md`.

- Inspect `git status` and existing files before editing.
- Keep the local STDIO MCP runnable with Python 3.12.
- Never commit tokens, `.env` files, databases, or customer media.
- Preserve the chat allowlist, dry-run default, explicit write execution, and
  refund guardrails in `core.py` and `server.py`.
- Run the focused tests before handoff. Do not push or deploy unless the user
  explicitly asks.
