import httpx

from assistant.main import _build_http_client


def test_build_http_client_returns_none_without_proxy() -> None:
    assert _build_http_client("", timeout=60.0) is None


async def test_build_http_client_uses_proxy_without_network_call() -> None:
    client = _build_http_client("http://user:pass@proxy.test:3128", timeout=60.0)

    assert isinstance(client, httpx.AsyncClient)
    assert client.timeout.read == 60.0

    await client.aclose()
