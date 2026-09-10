# Personal AI Assistant

A Telegram-based personal assistant using a DeepSeek-compatible chat-completions API. OpenRouter can
be used by setting `DEEPSEEK_BASE_URL` and `DEEPSEEK_MODEL`. The project is organized as a Python
package under `src/assistant`, with Telegram integration in `interfaces/telegram`, application
orchestration in `application`, and external AI providers in `infrastructure/ai`.

## Local setup

Requires Python 3.11 or newer.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Fill `.env` with the Telegram bot token and DeepSeek API key. Never commit `.env` or paste the key into source code, issues, or chat. The expected variables are documented in `.env.example`.

The bot accepts Telegram photos and sends them to the configured chat model as image content. Use
a vision-capable model, such as the Gemini model shown in `.env.example`, for image understanding.
Voice and audio messages use the OpenRouter transcription endpoint with the same key as
`DEEPSEEK_API_KEY` by default. The default model is `openai/gpt-4o-mini-transcribe` and the
language hint is Russian. Set `OPENAI_API_KEY` only when transcription should use a separate key;
`OPENAI_BASE_URL`, `OPENAI_TRANSCRIPTION_MODEL`, and `TRANSCRIPTION_LANGUAGE` can override the
defaults for another OpenAI-compatible provider.

Create a one-time reminder with the 24-hour `/remind HH:MM text` command, for example
`/remind 22:00 take the medicine`. The bot stores it in PostgreSQL and checks for due reminders
every minute. Times use `REMINDER_TIMEZONE` (default `Europe/Moscow`), not the Docker server's
timezone. A time that has already passed is scheduled for the next day. Use `/reminders` to view
pending reminders, `/edit_reminder ID HH:MM new text` to
change one, and `/remove_reminder ID` to delete one.

## Local Postgres and database layer

The supported local setup runs PostgreSQL 16 in Docker. Install Docker Desktop, then from the
repository root create the environment file and start the database:

```powershell
Copy-Item .env.example .env
docker compose --profile local up -d db
docker compose ps db
```

The container uses these development defaults:

| Setting | Value |
| --- | --- |
| Database | `assistant` |
| User | `assistant` |
| Password | `assistant_dev_password` |
| Host port | `5433` |

The database URL used by the application is
`postgresql+asyncpg://assistant:assistant_dev_password@localhost:5433/assistant`. Change the
`POSTGRES_*` values and `DATABASE_URL` together in `.env` if you need different credentials. The
database container must be recreated after changing `POSTGRES_*` values on an already-initialized
volume.

Apply all migrations after starting PostgreSQL:

```powershell
py -m alembic upgrade head
```

The current migration chain creates `conversation_messages`, `users`, `messages`,
`memory_entries`, and `reminders`. Check the current migration and roll back one migration with:

```powershell
py -m alembic current
py -m alembic downgrade -1
```

To remove the local database and all stored data deliberately:

```powershell
docker compose down -v
```

The database code lives under `src/assistant/infrastructure/db`. `create_session_factory` creates
an async SQLAlchemy session factory, and `session_scope` provides one transaction per application
operation: successful operations commit, while exceptions roll back and are re-raised. The
conversation store creates a missing `User` record before appending a `Message`.

Database schema and session tests use isolated SQLite databases or fakes, so they do not require
Docker. Run them with:

```powershell
\.venv\Scripts\python.exe -m pytest -q tests/test_schema.py tests/test_session.py tests/test_conversation_store.py
```

## Run and test the AI service standalone

The AI adapter is offline-testable and does not require Telegram, Docker, PostgreSQL, or a live API
key. From an activated virtual environment, install the project and development dependencies, then
run the focused tests:

```powershell
py -m pip install -e ".[dev]"
py -m pytest -q tests/test_deepseek.py
```

`DeepSeekAIService` accepts an injected `httpx.AsyncClient` for callers that need custom transport
or lifecycle control. Without one, it owns a reusable client; call `await service.aclose()` when the
embedding application shuts down. The adapter converts HTTP, transport, invalid-JSON, malformed
response, and empty-reply failures into `DeepSeekError`.

To make one live standalone completion without starting Telegram, run this PowerShell snippet after
setting `DEEPSEEK_API_KEY`:

```powershell
@'
import asyncio
import os

from assistant.domain.messages import ChatMessage
from assistant.infrastructure.ai.deepseek import DeepSeekAIService


async def main():
	service = DeepSeekAIService(
		api_key=os.environ["DEEPSEEK_API_KEY"],
		base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
		model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
	)
	try:
		print(await service.complete([ChatMessage(role="user", content="Reply with OK")]))
	finally:
		await service.aclose()


asyncio.run(main())
'@ | py
```

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

The full suite includes database-backed tests and requires the declared dependencies installed. It
does not require a running PostgreSQL server because the tests use isolated database fixtures. The
Telegram bot itself additionally requires Docker PostgreSQL and the migrations shown below.

To format changed Python files, run `ruff format .`.

## Run the bot

Start PostgreSQL in Docker and apply the database migrations before the first run and after schema
updates:

```powershell
docker compose --profile local up -d db
py -m alembic upgrade head
```

For local Docker Postgres, set `DATABASE_URL` to the Docker database URL shown above. The default
Compose deployment uses the `DATABASE_URL` from `.env` directly, which is suitable for Neon.
Then start
polling:

```powershell
py -m assistant.main
```

Stop the database with `docker compose stop db`. Data remains in the named Docker volume. Use
`docker compose down -v` only when you intentionally want to delete the database volume and all
stored conversations.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the branch and pull-request workflow.

## Deploy on a small VPS

The Compose stack can run the bot on a small Hetzner, DigitalOcean, or Oracle Cloud VPS while
using Neon for PostgreSQL. Install Docker Engine and the Compose plugin on the server, then clone
the repository and create `.env` from `.env.example`:

```sh
cp .env.example .env
```

Set the Telegram, AI, allowed-user, and Neon `DATABASE_URL` values in `.env`. The default Compose
path passes that Neon URL directly to the bot. The local Postgres service is available only with
the explicit `local` profile.

Start the stack from the repository root:

```sh
docker compose up -d --build
docker compose ps
docker compose logs -f bot
```

The bot applies pending Alembic migrations and then starts polling. It uses `restart:
unless-stopped`. Neon stores the database data independently of the VPS.

To deploy an update:

```sh
git pull
docker compose up -d --build
docker compose logs --tail=100 bot
```