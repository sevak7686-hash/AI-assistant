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

The database adapter is implemented behind the `ConversationStore` port; the reminder module is
still planned. Telegram must not query a database or call DeepSeek directly.

### Database session lifecycle

Create one session factory during application startup and inject it into database-backed
adapters. Each application operation or incoming request should use `session_scope(factory)` from
`infrastructure.db.session`:

```python
async with session_scope(session_factory) as session:
    await store.append(session=session, user_id=user_id, chat_id=chat_id, message=message)
```

`session_scope` commits when the block succeeds, rolls back when it raises, and closes the session
in both cases. Repositories and application services must not create engines or sessions directly,
and sessions must not be retained after the block exits. The factory and engine are process-scoped;
the session and transaction are operation-scoped. Startup/shutdown code owns eventual engine
disposal when the bot lifecycle is wired to persistence.

## Callable API contract

These are the function and protocol signatures that other application code should call. The
application-facing API uses domain objects so transport-specific types do not leak into the
use cases.

### Implemented now

```python
class ContextBuilder:
    def build(self, incoming: IncomingMessage) -> Sequence[ChatMessage]: ...


class AIService(Protocol):
    async def complete(self, messages: Sequence[ChatMessage]) -> str: ...


class ProcessMessage:
    async def execute(self, incoming: IncomingMessage) -> OutgoingMessage: ...


def build_telegram_app(
    settings: Settings,
    process_message: ProcessMessage,
) -> Application: ...
```

`ProcessMessage.execute` is the current equivalent of a `generate_response(user_id, text)`
facade. A future convenience facade may be added only if it preserves chat identity and returns
`OutgoingMessage`; callers should not call `DeepSeekAIService` directly.

### Ports

The following signatures are the boundaries for persistence and reminders. `ConversationStore` is
implemented by `SqlAlchemyConversationStore`; `ReminderScheduler` remains planned.

```python
class ConversationStore(Protocol):
    async def list_recent(
        self, *, user_id: int, chat_id: int, limit: int = 20
    ) -> Sequence[ChatMessage]: ...

    async def append(self, *, user_id: int, chat_id: int, message: ChatMessage) -> None: ...


class ReminderScheduler(Protocol):
    async def create(
        self, *, user_id: int, chat_id: int, text: str, due_at: datetime
    ) -> Reminder: ...

    async def claim_due(self, *, now: datetime, limit: int = 100) -> Sequence[Reminder]: ...

    async def mark_sent(self, *, reminder_id: int, sent_at: datetime) -> None: ...

    async def mark_retry(self, *, reminder_id: int, failed_at: datetime) -> None: ...
```

All async methods may raise an infrastructure-specific exception. The application layer owns
fallback behavior and logging; Telegram handlers only translate domain results into replies.

### Review status

This draft is ready to share with Dev2 and Dev3. Their feedback is still pending; no approval or
comments are recorded in this repository yet.

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

- `conversation_messages`: stable message id, user/chat identifiers, role, content, and created
    time. Roles are limited to `system`, `user`, and `assistant`; `content` stores the
    `ChatMessage.content` value. An index on `(user_id, chat_id, created_at)` supports the memory
    system's recent-history lookup, while the message id provides stable identity when timestamps
    are equal. Memory summaries or embeddings should be separate records so the raw conversation
    remains append-only.
- `messages`: normalized conversation records with the same user/chat, role, content, and time
    fields, linked to `users`. This is the persistence surface for new conversation-store code;
    `conversation_messages` remains for compatibility with the initial schema.
- `memory_entries`: user-owned durable memory content with a type, optional source message, and
    created/updated times. The user/created index supports retrieval by recency.
- `reminders`: user/chat identifier, text, due time, status, claimed time, sent time, retry count.

## When to split services

Do not split now. Reconsider only when one of these is true:

- reminder delivery needs independent uptime or scaling;
- AI calls need a separate queue and worker pool;
- multiple clients need a stable remote API;
- deployments or security boundaries require separate ownership.

If that point arrives, preserve the current ports as the migration boundary. Replace function calls with an internal HTTP or queue adapter one port at a time, beginning with reminder workers rather than splitting the whole application at once.
