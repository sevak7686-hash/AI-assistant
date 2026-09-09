from urllib.parse import parse_qsl, urlsplit

import pytest

from assistant.infrastructure.db.session import _async_database_url, session_scope


def test_plain_postgresql_urls_use_asyncpg() -> None:
    assert (
        _async_database_url("postgresql://user:pass@localhost/db?sslmode=require")
        == "postgresql+asyncpg://user:pass@localhost/db?ssl=require"
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
        "ssl": "require",
    }


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
