# Module Architecture

Status: accepted for the first production version.

## Decision

Build a **modular monolith** first. Telegram, the application use cases, the AI provider, persistence, and reminders run in one Python process and communicate through Python function calls and small protocols. They are separate modules with explicit ownership, but they are not separate deployable services yet.

This keeps the first version easy to run and debug, avoids distributed-systems overhead for a single-user assistant, and still leaves clear seams for replacing infrastructure later. A service split becomes worthwhile when there is independent scaling, deployment, or reliability pressure; it is not required by the current workload.

## Responsibilities and boundaries

| Module | Owns | Communicates through |
| --- | --- | --- |
| `interfaces.telegram` | Telegram updates, access checks, replies | `ProcessMessage.execute(IncomingMessage)` |
| `application` | Use-case orchestration and context assembly | Ports such as `AIService`, `ConversationStore`, and `ReminderScheduler` |
| `domain` | Message, conversation, and reminder data models | Plain Python values |
| `infrastructure.ai` | DeepSeek HTTP calls and provider errors | `AIService.complete(messages)` |
| `infrastructure.db` | Database schema and reads/writes | `ConversationStore` implementation |
| `infrastructure.reminders` | Due-time storage and delivery scheduling | `ReminderScheduler` implementation |

The database and reminder modules do not exist yet. They should be added behind application ports; Telegram must not query a database or call DeepSeek directly.

## Request flow

1. Telegram receives a text update and creates `IncomingMessage`.
2. `ProcessMessage` loads recent conversation history from `ConversationStore` and asks `ContextBuilder` to create the system, history, and current-user messages.
3. `AIService` sends that context to DeepSeek and returns assistant text.
4. `ProcessMessage` stores the user message and assistant reply through `ConversationStore`.
5. The application asks `ReminderScheduler` to create or update a reminder when the assistant has identified a reminder command. Reminder creation should be explicit and confirmed, not inferred from every casual mention of a date.
6. Telegram sends the resulting `OutgoingMessage` back to the chat.

The first implementation currently covers steps 1, 2, 3, and 6. Persistence and reminders are planned ports, not hidden global state.

## Reminder delivery flow

The reminder scheduler runs in the same process initially. On each tick it asks the store for due reminders, marks each one as claimed, and sends a domain event to an application delivery use case. That use case calls the Telegram gateway, which is the only module allowed to know Telegram transport details.

Reminder delivery must be idempotent: claiming a reminder before sending prevents duplicate sends after a retry. Failed sends remain retryable with a bounded retry policy.

## Database choice and evolution

Start with SQLite for local development and the first deployment. Keep SQL and connection management inside `infrastructure.db`; application code depends only on `ConversationStore` and reminder ports. PostgreSQL can replace SQLite later without changing Telegram or the use cases.

Suggested initial records:

- `conversation_messages`: user/chat identifier, role, text, created time.
- `reminders`: user/chat identifier, text, due time, status, claimed time, sent time, retry count.

## When to split services

Do not split now. Reconsider only when one of these is true:

- reminder delivery needs independent uptime or scaling;
- AI calls need a separate queue and worker pool;
- multiple clients need a stable remote API;
- deployments or security boundaries require separate ownership.

If that point arrives, preserve the current ports as the migration boundary. Replace function calls with an internal HTTP or queue adapter one port at a time, beginning with reminder workers rather than splitting the whole application at once.
