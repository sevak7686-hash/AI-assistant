import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from assistant.application.context_builder import ContextBuilder
from assistant.application.conversation_store import ConversationStore
from assistant.domain.messages import ChatMessage, IncomingMessage, OutgoingMessage
from assistant.infrastructure.ai.service import AICompletion, AIService, ToolDefinition
from assistant.infrastructure.search.serpapi import SearchError

logger = logging.getLogger(__name__)

_FALLBACK_REPLY = "I hit a problem generating a reply. Please try again in a moment."


class ProcessMessage:
    def __init__(
        self,
        *,
        ai_service: AIService,
        context_builder: ContextBuilder,
        conversation_store: ConversationStore | None = None,
        search_service=None,
        reminder_store=None,
        reminder_timezone: ZoneInfo | None = None,
        max_tool_rounds: int = 2,
    ) -> None:
        self._ai_service = ai_service
        self._context_builder = context_builder
        self._conversation_store = conversation_store
        self._search_service = search_service
        self._reminder_store = reminder_store
        self._reminder_timezone = reminder_timezone or ZoneInfo("UTC")
        self._max_tool_rounds = max(0, max_tool_rounds)

    async def execute(self, incoming: IncomingMessage) -> OutgoingMessage:
        history: list[ChatMessage] = []
        if self._conversation_store is not None:
            try:
                history = list(
                    await self._conversation_store.list_recent(
                        user_id=incoming.user_id, chat_id=incoming.chat_id
                    )
                )
            except Exception:
                logger.exception(
                    "Conversation history lookup failed for user_id=%s", incoming.user_id
                )

        context = self._context_builder.build(incoming, history)
        try:
            reply, transcript = await self._complete(
                context, user_id=incoming.user_id, chat_id=incoming.chat_id
            )
        except Exception:
            logger.exception("AI completion failed for user_id=%s", incoming.user_id)
            reply = _FALLBACK_REPLY
        else:
            if self._conversation_store is not None:
                try:
                    await self._conversation_store.append(
                        user_id=incoming.user_id,
                        chat_id=incoming.chat_id,
                        message=ChatMessage(role="user", content=incoming.text),
                    )
                    for message in transcript:
                        await self._conversation_store.append(
                            user_id=incoming.user_id,
                            chat_id=incoming.chat_id,
                            message=message,
                        )
                    await self._conversation_store.append(
                        user_id=incoming.user_id,
                        chat_id=incoming.chat_id,
                        message=ChatMessage(role="assistant", content=reply),
                    )
                except Exception:
                    logger.exception(
                        "Conversation persistence failed for user_id=%s", incoming.user_id
                    )
        return OutgoingMessage(chat_id=incoming.chat_id, text=reply)

    async def _complete(
        self,
        context: list[ChatMessage] | tuple[ChatMessage, ...],
        *,
        user_id: int,
        chat_id: int,
    ) -> tuple[str, list[ChatMessage]]:
        if (
            self._search_service is None and self._reminder_store is None
        ) or self._max_tool_rounds == 0:
            result = await self._ai_service.complete(context)
            return _completion_text(result), []

        available_tools = (_WEB_SEARCH_TOOL,)
        if self._reminder_store is not None:
            available_tools += (
                _CREATE_REMINDER_TOOL,
                _LIST_REMINDERS_TOOL,
                _UPDATE_REMINDER_TOOL,
                _DELETE_REMINDER_TOOL,
            )
        tools = tuple(
            tool
            for tool in available_tools
            if tool["function"]["name"] != "web_search" or self._search_service is not None
        )
        working = list(context)
        transcript: list[ChatMessage] = []
        for _ in range(self._max_tool_rounds + 1):
            result = await self._ai_service.complete(working, tools=tools)
            completion = _as_completion(result)
            if not completion.tool_calls:
                if not completion.content:
                    raise RuntimeError("AI returned an empty final reply")
                return completion.content, transcript
            assistant_message = ChatMessage(
                role="assistant", content=completion.content, tool_calls=completion.tool_calls
            )
            working.append(assistant_message)
            transcript.append(assistant_message)
            for tool_call in completion.tool_calls:
                if tool_call.name == "web_search":
                    if self._search_service is None:
                        raise RuntimeError("Web search is not configured")
                    result_content = await self._run_web_search(tool_call.arguments)
                elif tool_call.name == "create_reminder":
                    if self._reminder_store is None:
                        raise RuntimeError("Reminders are not configured")
                    result_content = await self._create_reminder(
                        tool_call.arguments, user_id=user_id, chat_id=chat_id
                    )
                elif tool_call.name == "list_reminders":
                    result_content = await self._list_reminders(user_id=user_id)
                elif tool_call.name == "update_reminder":
                    result_content = await self._update_reminder(
                        tool_call.arguments, user_id=user_id
                    )
                elif tool_call.name == "delete_reminder":
                    result_content = await self._delete_reminder(
                        tool_call.arguments, user_id=user_id
                    )
                else:
                    raise RuntimeError(f"Unsupported tool: {tool_call.name}")
                tool_message = ChatMessage(
                    role="tool", content=result_content, tool_call_id=tool_call.id
                )
                working.append(tool_message)
                transcript.append(tool_message)
        raise RuntimeError("AI exceeded the maximum web search tool rounds")

    async def _run_web_search(self, arguments: str) -> str:
        try:
            parsed = json.loads(arguments)
            query = parsed["query"]
        except (json.JSONDecodeError, KeyError, TypeError):
            raise RuntimeError("AI returned invalid web search arguments") from None
        if not isinstance(query, str) or not query.strip() or len(query) > 500:
            raise RuntimeError("AI returned an invalid web search query")
        try:
            results = await self._search_service.search(query.strip())
        except SearchError as exc:
            logger.warning("Web search failed: %s", exc)
            return json.dumps(
                {"error": "Web search is temporarily unavailable. Do not invent current facts."},
                ensure_ascii=False,
            )
        return json.dumps(
            [{"title": item.title, "url": item.url, "snippet": item.snippet} for item in results],
            ensure_ascii=False,
        )

    async def _create_reminder(self, arguments: str, *, user_id: int, chat_id: int) -> str:
        try:
            parsed = json.loads(arguments)
            text = parsed["text"]
            due_at_value = parsed["due_at"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return json.dumps({"error": "Reminder needs text and due_at."}, ensure_ascii=False)
        if not isinstance(text, str) or not text.strip() or len(text) > 1000:
            return json.dumps({"error": "Reminder text is invalid."}, ensure_ascii=False)
        if not isinstance(due_at_value, str):
            return json.dumps(
                {"error": "Reminder due_at must be an ISO timestamp."}, ensure_ascii=False
            )
        try:
            due_at = datetime.fromisoformat(due_at_value)
        except ValueError:
            return json.dumps(
                {"error": "Reminder due_at must be an ISO timestamp."}, ensure_ascii=False
            )
        due_at = self._normalize_future_time(due_at)
        if due_at is None:
            return json.dumps(
                {"error": "Reminder due_at must be in the future."}, ensure_ascii=False
            )
        reminder = await self._reminder_store.create(
            user_id=user_id, chat_id=chat_id, text=text.strip(), due_at=due_at
        )
        return json.dumps(
            {
                "created": True,
                "id": reminder.id,
                "text": reminder.text,
                "due_at": reminder.due_at.isoformat(),
            },
            ensure_ascii=False,
        )

    async def _list_reminders(self, *, user_id: int) -> str:
        reminders = await self._reminder_store.list_pending(user_id=user_id)
        return json.dumps(
            [
                {
                    "id": reminder.id,
                    "text": reminder.text,
                    "due_at": reminder.due_at.astimezone(self._reminder_timezone).isoformat(),
                }
                for reminder in reminders
            ],
            ensure_ascii=False,
        )

    async def _update_reminder(self, arguments: str, *, user_id: int) -> str:
        try:
            parsed = json.loads(arguments)
            reminder_id = parsed["id"]
            text = parsed["text"]
            due_at_value = parsed["due_at"]
            due_at = datetime.fromisoformat(due_at_value)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return json.dumps({"error": "Update needs id, text, and due_at."}, ensure_ascii=False)
        if not isinstance(reminder_id, int) or not isinstance(text, str) or not text.strip():
            return json.dumps({"error": "Reminder id and text are invalid."}, ensure_ascii=False)
        due_at = self._normalize_future_time(due_at)
        if due_at is None:
            return json.dumps(
                {"error": "Reminder due_at must be in the future."}, ensure_ascii=False
            )
        reminder = await self._reminder_store.update_pending(
            user_id=user_id, reminder_id=reminder_id, text=text.strip(), due_at=due_at
        )
        if reminder is None:
            return json.dumps(
                {"updated": False, "error": "Reminder not found."}, ensure_ascii=False
            )
        return json.dumps(
            {
                "updated": True,
                "id": reminder.id,
                "text": reminder.text,
                "due_at": reminder.due_at.isoformat(),
            },
            ensure_ascii=False,
        )

    async def _delete_reminder(self, arguments: str, *, user_id: int) -> str:
        try:
            reminder_id = json.loads(arguments)["id"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return json.dumps({"error": "Delete needs a reminder id."}, ensure_ascii=False)
        if not isinstance(reminder_id, int):
            return json.dumps({"error": "Reminder id is invalid."}, ensure_ascii=False)
        deleted = await self._reminder_store.delete_pending(
            user_id=user_id, reminder_id=reminder_id
        )
        return json.dumps({"deleted": deleted, "id": reminder_id}, ensure_ascii=False)

    def _normalize_future_time(self, value: datetime) -> datetime | None:
        if value.tzinfo is None:
            value = value.replace(tzinfo=self._reminder_timezone)
        value = value.astimezone(self._reminder_timezone)
        return value if value > datetime.now(self._reminder_timezone) else None


def _as_completion(result: AICompletion | str) -> AICompletion:
    return result if isinstance(result, AICompletion) else AICompletion(content=result)


def _completion_text(result: AICompletion | str) -> str:
    completion = _as_completion(result)
    if completion.tool_calls:
        raise RuntimeError("AI requested a tool without search being configured")
    if not completion.content:
        raise RuntimeError("AI returned an empty reply")
    return completion.content


_WEB_SEARCH_TOOL: ToolDefinition = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the internet for current or externally verified information.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "The search query."}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

_CREATE_REMINDER_TOOL: ToolDefinition = {
    "type": "function",
    "function": {
        "name": "create_reminder",
        "description": "Create a reminder after the user clearly provides what and when.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "What to remind the user about."},
                "due_at": {
                    "type": "string",
                    "description": "Future ISO 8601 timestamp, including timezone offset.",
                },
            },
            "required": ["text", "due_at"],
            "additionalProperties": False,
        },
    },
}

_LIST_REMINDERS_TOOL: ToolDefinition = {
    "type": "function",
    "function": {
        "name": "list_reminders",
        "description": "List the user's pending reminders.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}

_UPDATE_REMINDER_TOOL: ToolDefinition = {
    "type": "function",
    "function": {
        "name": "update_reminder",
        "description": "Edit a pending reminder by id, text, and future ISO timestamp.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "text": {"type": "string"},
                "due_at": {"type": "string", "description": "Future ISO 8601 timestamp."},
            },
            "required": ["id", "text", "due_at"],
            "additionalProperties": False,
        },
    },
}

_DELETE_REMINDER_TOOL: ToolDefinition = {
    "type": "function",
    "function": {
        "name": "delete_reminder",
        "description": "Delete a pending reminder by id.",
        "parameters": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
            "additionalProperties": False,
        },
    },
}
