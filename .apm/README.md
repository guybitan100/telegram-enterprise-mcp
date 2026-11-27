# Telegram Enterprise MCP agent package

This package contains the agent, skill, and repository instructions for the
local Telegram Enterprise MCP. The application itself is a Python STDIO MCP
server, not a generic bot template or a deployed service.

## Package contents

- [`agents/telegram-engineer.agent.md`](./agents/telegram-engineer.agent.md):
  production-oriented Telegram MCP agent.
- [`agents/code-reviewer.agent.md`](./agents/code-reviewer.agent.md): focused
  security and correctness reviewer for the MCP and NOVA bot.
- [`skills/telegram-bot-builder/SKILL.md`](./skills/telegram-bot-builder/SKILL.md):
  implementation and safety workflow.
- [`instructions/repository.instructions.md`](./instructions/repository.instructions.md):
  repository-wide guardrails.
- [`instructions/copilot.instructions.md`](./instructions/copilot.instructions.md):
  coding-assistant entry point.

Use the root [`README.md`](../README.md) for setup, environment variables,
runtime behavior, and production limitations. BotFather setup, credentials,
deployment, and live payment testing remain manual and explicit.

APM can install this package into the target agent runtime with `apm install`.
