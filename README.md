# Personal AI Assistant

A Telegram-based personal assistant powered through OpenRouter. The project is organized as a Python package under `src/assistant`, with Telegram integration in `interfaces/telegram`, application orchestration in `application`, and external AI providers in `infrastructure/ai`.

## Local setup

Requires Python 3.11 or newer.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Fill `.env` with the Telegram bot token and DeepSeek API key. Never commit `.env` or paste the key into source code, issues, or chat. The expected variables are documented in `.env.example`.

## OpenRouter smoke test

After setting `DEEPSEEK_API_KEY` in the current shell, make one raw request through OpenRouter:

```powershell
curl.exe -sS https://openrouter.ai/api/v1/chat/completions `
	-H "Authorization: Bearer $env:DEEPSEEK_API_KEY" `
	-H "Content-Type: application/json" `
	-d '{"model":"google/gemini-2.5-flash","messages":[{"role":"user","content":"Reply with OK"}]}'
```

A successful response contains `choices[0].message.content`. A `401` response means the key is missing, invalid, or revoked; do not commit or share it while troubleshooting.

## Architecture and prompt evaluation

The first version is a modular monolith: Telegram, application use cases, DeepSeek, persistence, and reminders communicate through in-process Python interfaces. See [docs/architecture.md](docs/architecture.md) for the boundaries and the path to a later service split.

The initial assistant system prompt is in `src/assistant/application/prompts.py`. Before changing it, evaluate these two conversations through the configured DeepSeek endpoint:

1. User: `Remind me tomorrow to call Sam.` Expected behavior: ask for a time or explain that a reminder can only be created after the application confirms the schedule; do not claim it was saved.
2. User: `I have 3 tasks and 30 minutes. Help me choose.` Expected behavior: ask for or use the task list, make a practical prioritization, and keep the answer concise.

Use the smoke-test command above with the system prompt and each user message. Record the model reply, model name, date, and whether it met the expected behavior in the issue or task notes. This is an integration check and requires a valid `DEEPSEEK_API_KEY`; unit tests remain offline and deterministic.

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