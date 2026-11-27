# Telegram Enterprise MCP v0.1
Local STDIO MCP starter. Python 3.12 recommended. Create bot with BotFather, grant minimal channel admin permissions. Use only content you own or license.

## Run
`python -m venv .venv` then `source .venv/bin/activate`, `pip install -r requirements.txt`.
Export variables from `.env.example` manually (do not commit secrets). Run `python server.py` via an MCP client. Example client config:
```json
{"mcpServers":{"telegram":{"command":"/absolute/path/.venv/bin/python","args":["/absolute/path/server.py"],"env":{"TELEGRAM_BOT_TOKEN":"REPLACE_LOCALLY","TELEGRAM_ALLOWED_CHATS":"@my_channel","TELEGRAM_ENABLE_WRITES":"false"}}}}
```
Docker: `docker build -t telegram-mcp .` then `docker run --rm -i --env-file .env telegram-mcp`.
Tests: `pip install pytest` then `python -m pytest -q`.

## Safety and limitations
Writes require both environment enablement and execute=true. This is not human approval; configure client approvals and restrict access. Use exact chat allowlist; prefer numeric IDs. Refunds have separate enablement and apply to supported bot invoice payments, not arbitrary channel purchases. Bot balance is not channel revenue. File IDs must already be available to this bot. No automatic write retries because outcomes may be ambiguous. Audit logging is minimal; configure HTTP library logging carefully to avoid token leakage. Invoice creation alone does not fulfill orders: do not enable invoice sales before implementing pre_checkout_query handling (within 10 seconds), successful_payment verification, durable idempotency and delivery. No user-account scraping or arbitrary history access. No remote endpoint exposed.

## Production roadmap
1. Durable order and payment service, webhook secret verification, deduplication and fulfillment; support /paysupport.
2. S3 media ingestion, size validation, local Bot API server for large uploads, scheduler and promotion state.
3. Remote Streamable HTTP MCP with OAuth, per-principal authorization, approval workflow, immutable audit, rate limits and tenant isolation.
4. AWS ECS Fargate, ALB, Secrets Manager, DynamoDB, SQS, EventBridge, CloudWatch and Terraform; CI integration and sandbox tests.
5. ChatGPT connection subject to account/client support for custom remote MCP tools. STDIO is for compatible local clients.

References: https://core.telegram.org/bots/api ; https://core.telegram.org/bots/payments-stars ; https://modelcontextprotocol.io/
