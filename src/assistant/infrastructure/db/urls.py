from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def sync_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        sync_url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgres://"):
        sync_url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    else:
        sync_url = url.replace("postgresql+asyncpg", "postgresql+psycopg2", 1).replace(
            "sqlite+aiosqlite", "sqlite", 1
        )
    if "postgresql+psycopg2" in sync_url:
        parts = urlsplit(sync_url)
        query = dict(parse_qsl(parts.query))
        if "ssl" in query:
            query["sslmode"] = query.pop("ssl")
        if query.get("sslmode") in {"verify-ca", "verify-full"} and "sslrootcert" not in query:
            query["sslrootcert"] = "system"
        sync_url = urlunsplit(parts._replace(query=urlencode(query)))
    return sync_url
