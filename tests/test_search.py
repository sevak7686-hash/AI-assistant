import httpx
import pytest

from assistant.infrastructure.search.serpapi import SearchError, SerpAPIWebSearch


async def test_serpapi_normalizes_results() -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "organic_results": [
                    {"title": "Example", "link": "https://example.test", "snippet": "A result."}
                ]
            }

    class FakeClient:
        async def get(self, url, *, params):
            assert url == "https://serpapi.com/search.json"
            assert params["q"] == "latest news"
            assert params["hl"] == "ru"
            assert params["gl"] == "ru"
            return FakeResponse()

        async def aclose(self) -> None:
            return None

    results = await SerpAPIWebSearch(api_key="key", client=FakeClient()).search("latest news")

    assert results[0].title == "Example"
    assert results[0].url == "https://example.test"


async def test_serpapi_http_errors_are_wrapped() -> None:
    request = httpx.Request("GET", "https://serpapi.com/search.json")
    response = httpx.Response(503, request=request, text="unavailable")

    class FakeClient:
        async def get(self, url, *, params):
            raise httpx.HTTPStatusError("failed", request=request, response=response)

    with pytest.raises(SearchError, match="HTTP 503"):
        await SerpAPIWebSearch(api_key="key", client=FakeClient()).search("query")


async def test_serpapi_transport_errors_include_exception_type() -> None:
    class FakeClient:
        async def get(self, url, *, params):
            raise httpx.ReadTimeout("timed out")

    with pytest.raises(SearchError, match="ReadTimeout"):
        await SerpAPIWebSearch(api_key="key", client=FakeClient()).search("query")
