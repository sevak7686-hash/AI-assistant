# Personal AI Assistant

A Telegram-based personal assistant powered by DeepSeek. The project is organized as a Python package under `src/assistant`, with Telegram integration in `interfaces/telegram`, application orchestration in `application`, and external AI providers in `infrastructure/ai`.

## Local setup

Requires Python 3.11 or newer.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Fill `.env` with the Telegram bot token and DeepSeek API key. Never commit `.env` or paste the key into source code, issues, or chat. The expected variables are documented in `.env.example`.

## DeepSeek smoke test

After setting `DEEPSEEK_API_KEY` in the current shell, make one raw request through OpenRouter:

```powershell
curl.exe -sS https://openrouter.ai/api/v1/chat/completions `
	-H "Authorization: Bearer $env:DEEPSEEK_API_KEY" `
	-H "Content-Type: application/json" `
	-d '{"model":"deepseek/deepseek-chat","messages":[{"role":"user","content":"Reply with OK"}]}'
```

A successful response contains `choices[0].message.content`. A `401` response means the key is missing, invalid, or revoked; do not commit or share it while troubleshooting.

## Development checks

Run these before opening a pull request:

```powershell
ruff check .
ruff format --check .
pytest
```

To format changed Python files, run `ruff format .`.

## Run the bot

```powershell
py -m assistant.main
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the branch and pull-request workflow.