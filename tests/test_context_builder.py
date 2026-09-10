from assistant.application.context_builder import ContextBuilder
from assistant.application.prompts import SYSTEM_PROMPT
from assistant.domain.messages import ChatMessage, IncomingMessage, ToolCall


def test_build_includes_system_and_user_messages() -> None:
    builder = ContextBuilder(system_prompt="You are a test assistant.")
    incoming = IncomingMessage(user_id=1, chat_id=1, text="Hello")

    messages = builder.build(incoming)

    assert len(messages) == 2
    assert messages[0].role == "system"
    assert messages[0].content == "You are a test assistant."
    assert messages[1].role == "user"
    assert messages[1].content == "Hello"


def test_default_prompt_sets_capability_and_truthfulness_boundaries() -> None:
    messages = ContextBuilder().build(
        IncomingMessage(user_id=1, chat_id=1, text="Remind me tomorrow")
    )

    assert messages[0].content == SYSTEM_PROMPT
    assert "do not claim that a reminder was created" in SYSTEM_PROMPT
    assert "Do not invent facts" in SYSTEM_PROMPT


def test_build_preserves_multimodal_user_content() -> None:
    content = [
        {"type": "text", "text": "What is this?"},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,aW1hZ2U="}},
    ]

    messages = ContextBuilder().build(
        IncomingMessage(user_id=1, chat_id=1, text="[Image]", content=content)
    )

    assert messages[-1].content == content


def test_build_excludes_persisted_tool_transcript_from_new_turn() -> None:
    builder = ContextBuilder(system_prompt="system")
    history = [
        ChatMessage(role="user", content="Search this"),
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=(ToolCall(id="call-1", name="web_search", arguments='{"query":"x"}'),),
        ),
        ChatMessage(role="tool", content="results", tool_call_id="call-1"),
        ChatMessage(role="assistant", content="Final answer"),
    ]

    messages = builder.build(IncomingMessage(user_id=1, chat_id=1, text="Next"), history)

    assert [message.role for message in messages] == ["system", "user", "assistant", "user"]
    assert messages[-2].content == "Final answer"
