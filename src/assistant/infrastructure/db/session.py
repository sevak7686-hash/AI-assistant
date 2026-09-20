import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from assistant.config import Settings


def _async_database_config(url: str) -> tuple[str, dict[str, ssl.SSLContext]]:
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)

    connect_args: dict[str, ssl.SSLContext] = {}
    if url.startswith("postgresql+asyncpg://"):
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        sslmode = query.pop("sslmode", "")
        sslrootcert = query.pop("sslrootcert", "")
        if sslmode in {"verify-full", "verify-ca"}:
            connect_args["ssl"] = ssl.create_default_context(cafile=sslrootcert or None)
        elif sslmode == "require":
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connect_args["ssl"] = ssl_context
        url = urlunsplit(parts._replace(query=urlencode(query)))
    return url, connect_args


def _async_database_url(url: str) -> str:
    return _async_database_config(url)[0]


def create_session_factory(url: str | None = None) -> async_sessionmaker[AsyncSession]:
    database_url, connect_args = _async_database_config(url or Settings().database_url)
    engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args=connect_args,
    )
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
