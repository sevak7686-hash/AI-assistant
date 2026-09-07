import pytest

from assistant.infrastructure.db.session import session_scope


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
