import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from assistant.infrastructure.db.base import Base
from assistant.infrastructure.db.models import ConversationMessage


def _load_users_migration():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "0002_users.py"
    spec = importlib.util.spec_from_file_location("users_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _load_memory_messages_migration():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "0003_memory_entries_messages.py"
    spec = importlib.util.spec_from_file_location("memory_messages_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_conversation_message_schema_supports_recent_memory_lookup() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    inspector = inspect(engine)
    columns = {
        column["name"] for column in inspector.get_columns(ConversationMessage.__tablename__)
    }
    indexes = {index["name"] for index in inspector.get_indexes(ConversationMessage.__tablename__)}

    assert columns == {"id", "user_id", "chat_id", "role", "content", "created_at"}
    assert "ix_conversation_messages_conversation_created" in indexes


def test_users_migration_can_create_and_rollback() -> None:
    engine = create_engine("sqlite://")
    connection = engine.connect()
    migration = _load_users_migration()
    context = MigrationContext.configure(connection)

    with Operations.context(context):
        migration.upgrade()

    assert "users" in inspect(connection).get_table_names()
    assert {column["name"] for column in inspect(connection).get_columns("users")} == {
        "id",
        "username",
        "first_name",
        "last_name",
        "created_at",
    }

    with Operations.context(context):
        migration.downgrade()

    assert "users" not in inspect(connection).get_table_names()


def test_memory_entries_messages_migration_can_create_and_rollback() -> None:
    engine = create_engine("sqlite://")
    connection = engine.connect()
    users_migration = _load_users_migration()
    memory_messages_migration = _load_memory_messages_migration()
    users_context = MigrationContext.configure(connection)

    with Operations.context(users_context):
        users_migration.upgrade()
        memory_messages_migration.upgrade()

    inspector = inspect(connection)
    assert {"messages", "memory_entries"}.issubset(inspector.get_table_names())
    assert {column["name"] for column in inspector.get_columns("messages")} == {
        "id",
        "user_id",
        "chat_id",
        "role",
        "content",
        "created_at",
    }
    assert {column["name"] for column in inspector.get_columns("memory_entries")} == {
        "id",
        "user_id",
        "source_message_id",
        "memory_type",
        "content",
        "created_at",
        "updated_at",
    }
    assert "ix_messages_conversation_created" in {
        index["name"] for index in inspector.get_indexes("messages")
    }
    assert "ix_memory_entries_user_created" in {
        index["name"] for index in inspector.get_indexes("memory_entries")
    }

    with Operations.context(users_context):
        memory_messages_migration.downgrade()

    assert not {"messages", "memory_entries"}.intersection(inspect(connection).get_table_names())
