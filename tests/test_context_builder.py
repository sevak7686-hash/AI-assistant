from assistant.application.context_builder import ContextBuilder
from assistant.domain.messages import IncomingMessage


def test_build_includes_system_and_user_messages() -> None:
    builder = ContextBuilder(system_prompt="You are a test assistant.")
    incoming = IncomingMessage(user_id=1, chat_id=1, text="Hello")

    messages = builder.build(incoming)

    assert len(messages) == 2
    assert messages[0].role == "system"
    assert messages[0].content == "You are a test assistant."
    assert messages[1].role == "user"
    assert messages[1].content == "Hello"
