from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class SearchError(RuntimeError):
    pass


class SerpAPIWebSearch:
    def __init__(
        self,
        *,
        api_key: str,
        max_results: int = 5,
        timeout_seconds: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("SerpAPI key must not be empty")
        if not 1 <= max_results <= 10:
            raise ValueError("SerpAPI max_results must be between 1 and 10")
        self._api_key = api_key
        self._max_results = max_results
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(self, query: str) -> list[SearchResult]:
        if not query.strip() or len(query) > 500:
            raise SearchError("Search query must contain 1 to 500 characters")
        try:
            response = await self._client.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google",
                    "q": query,
                    "api_key": self._api_key,
                    "num": self._max_results,
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SearchError(
                f"SerpAPI HTTP {exc.response.status_code}: {exc.response.text[:300]}"
            ) from None
        except httpx.HTTPError as exc:
            raise SearchError(
                f"SerpAPI request failed ({type(exc).__name__}): {exc or 'no detail'}"
            ) from None

        try:
            data = response.json()
            organic_results = data.get("organic_results", [])
        except (ValueError, AttributeError) as exc:
            raise SearchError("SerpAPI returned invalid JSON") from exc
        if not isinstance(organic_results, list):
            raise SearchError("SerpAPI returned an unexpected response shape")

        results: list[SearchResult] = []
        for item in organic_results[: self._max_results]:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            url = item.get("link")
            snippet = item.get("snippet", "")
            if isinstance(title, str) and isinstance(url, str) and isinstance(snippet, str):
                results.append(
                    SearchResult(title=title[:500], url=url[:2000], snippet=snippet[:2000])
                )
        return results
