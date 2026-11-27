# Repository guidance

This folder contains instructions for coding agents working on the local
Telegram Enterprise MCP. The application is a Python STDIO MCP server, not a
generic bot template or a deployed service.

## Files

- [`AGENTS.md`](./AGENTS.md): repository-wide guardrails.
- [`SKILL.md`](./SKILL.md): implementation and safety workflow.
- [`telegram-engineer.agent.md`](./telegram-engineer.agent.md): optional custom
  agent profile.
- [`copilot-instructions.md`](./copilot-instructions.md): Copilot entry point.

Use the root [`README.md`](../README.md) for setup, environment variables,
runtime behavior, and production limitations. BotFather setup, credentials,
deployment, and live payment testing remain manual and explicit.
