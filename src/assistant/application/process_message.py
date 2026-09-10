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

        tools = tuple(
            tool
            for tool in (_WEB_SEARCH_TOOL, _CREATE_REMINDER_TOOL)
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
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=self._reminder_timezone)
        due_at = due_at.astimezone(self._reminder_timezone)
        if due_at <= datetime.now(self._reminder_timezone):
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
