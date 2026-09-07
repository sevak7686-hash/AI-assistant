from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from assistant.config import Settings


def create_session_factory(url: str | None = None) -> async_sessionmaker[AsyncSession]:
    database_url = url or Settings().database_url
    engine = create_async_engine(database_url, echo=False)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Provide one transaction-scoped session for an application operation."""
    async with session_factory() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
        else:
            await session.commit()
