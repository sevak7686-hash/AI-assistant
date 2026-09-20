import ssl
from urllib.parse import parse_qsl, urlsplit

import pytest

from assistant.infrastructure.db.session import (
    _async_database_config,
    _async_database_url,
    session_scope,
)


def test_plain_postgresql_urls_use_asyncpg() -> None:
    assert (
        _async_database_url("postgresql://user:pass@localhost/db?sslmode=require")
        == "postgresql+asyncpg://user:pass@localhost/db"
    )
    assert (
        _async_database_url("postgres://user:pass@localhost/db")
        == "postgresql+asyncpg://user:pass@localhost/db"
    )


def test_async_database_urls_are_unchanged() -> None:
    url = "postgresql+asyncpg://user:pass@localhost/db"

    assert _async_database_url(url) == url


def test_async_database_url_preserves_other_query_parameters() -> None:
    url = "postgresql+asyncpg://user:pass@localhost/db?sslmode=require&channel_binding=require"
    normalized = _async_database_url(url)

    assert urlsplit(normalized).scheme == "postgresql+asyncpg"
    assert dict(parse_qsl(urlsplit(normalized).query)) == {
        "channel_binding": "require",
    }


def test_async_database_config_translates_require_ssl() -> None:
    normalized, connect_args = _async_database_config(
        "postgresql://user:pass@localhost/db?sslmode=require&sslrootcert=/tmp/ca.pem"
    )

    assert normalized == "postgresql+asyncpg://user:pass@localhost/db"
    ssl_context = connect_args["ssl"]
    assert ssl_context.check_hostname is False
    assert ssl_context.verify_mode.value == 0


def test_async_database_config_uses_default_context_for_verified_ssl(monkeypatch) -> None:
    original_create_default_context = ssl.create_default_context
    captured: dict[str, str | None] = {}

    def create_default_context(*, cafile=None):
        captured["cafile"] = cafile
        return original_create_default_context()

    monkeypatch.setattr(
        "assistant.infrastructure.db.session.ssl.create_default_context", create_default_context
    )
    normalized, connect_args = _async_database_config(
        "postgresql://user:pass@localhost/db?sslmode=verify-full&sslrootcert=/tmp/provider-ca.pem"
    )

    assert normalized == "postgresql+asyncpg://user:pass@localhost/db"
    assert captured["cafile"] == "/tmp/provider-ca.pem"
    ssl_context = connect_args["ssl"]
    assert ssl_context.check_hostname is True
    assert ssl_context.verify_mode.value == 2


def test_async_database_config_disables_ssl_when_absent_or_disabled() -> None:
    _, no_ssl_args = _async_database_config("postgresql://user:pass@localhost/db")
    _, disabled_ssl_args = _async_database_config(
        "postgresql://user:pass@localhost/db?sslmode=disable&sslrootcert=/tmp/ca.pem"
    )

    assert no_ssl_args == {}
    assert disabled_ssl_args == {}


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.closed = True

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeSessionFactory:
    def __init__(self) -> None:
        self.session = FakeSession()

    def __call__(self) -> FakeSession:
        return self.session


async def test_session_scope_commits_and_closes_on_success() -> None:
    factory = FakeSessionFactory()

    async with session_scope(factory) as session:
        assert session is factory.session

    assert factory.session.commits == 1
    assert factory.session.rollbacks == 0
    assert factory.session.closed is True


async def test_session_scope_rolls_back_closes_and_reraises() -> None:
    factory = FakeSessionFactory()

    with pytest.raises(RuntimeError, match="operation failed"):
        async with session_scope(factory):
            raise RuntimeError("operation failed")

    assert factory.session.commits == 0
    assert factory.session.rollbacks == 1
    assert factory.session.closed is True
