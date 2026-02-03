"""
SearchToolkit - Web search capabilities for agents.

Ported from CAMEL-AI/Eigent project.
Supports Google Custom Search API with fallback to DuckDuckGo.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from .base_toolkit import BaseToolkit, FunctionTool
from ...events import listen_toolkit

logger = logging.getLogger(__name__)

# Try to import httpx for async HTTP requests
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning("httpx not available, SearchToolkit will have limited functionality")


class SearchToolkit(BaseToolkit):
    """A toolkit for web search capabilities.

    Supports Google Custom Search API with automatic fallback to DuckDuckGo
    if API keys are not configured.
    Uses @listen_toolkit for automatic event emission on public methods.
    """

    # Agent name for event tracking
    agent_name: str = "search_agent"

    def __init__(
        self,
        google_api_key: Optional[str] = None,
        search_engine_id: Optional[str] = None,
        timeout: Optional[float] = 30.0,
    ) -> None:
        """Initialize the SearchToolkit.

        Args:
            google_api_key: Google Custom Search API key. If not provided,
                will try to get from GOOGLE_API_KEY environment variable.
            search_engine_id: Google Custom Search Engine ID. If not provided,
                will try to get from SEARCH_ENGINE_ID environment variable.
            timeout: Request timeout in seconds.
        """
        super().__init__(timeout=timeout)

        self._google_api_key = google_api_key or os.environ.get("GOOGLE_API_KEY")
        self._search_engine_id = search_engine_id or os.environ.get("SEARCH_ENGINE_ID")

        self._has_google_api = bool(self._google_api_key and self._search_engine_id)

        if self._has_google_api:
            logger.info("SearchToolkit initialized with Google Custom Search API")
        else:
            logger.info("SearchToolkit initialized with DuckDuckGo fallback")

    @listen_toolkit(
        inputs=lambda self, query, num_results=10: f"Searching: {query[:50]}{'...' if len(query) > 50 else ''}",
        return_msg=lambda r: f"Found {r.count(chr(10)) - 2} results" if "Found" in r else r[:100]
    )
    async def search_google(
        self,
        query: str,
        num_results: int = 10,
    ) -> str:
        """Search the web using Google or DuckDuckGo.

        Args:
            query: The search query string.
            num_results: Maximum number of results to return (default 10).

        Returns:
            Formatted string with search results, each containing title, URL, and snippet.
        """
        if not HTTPX_AVAILABLE:
            return "Error: httpx library not available for search"

        if self._has_google_api:
            results = await self._search_google_api(query, num_results)
        else:
            results = await self._search_duckduckgo(query, num_results)

        return self._format_results(results)

    async def _search_google_api(
        self,
        query: str,
        num_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search using Google Custom Search API."""
        try:
            results = []
            # Google API returns max 10 results per request
            pages_needed = (num_results + 9) // 10

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                for page in range(pages_needed):
                    start_index = page * 10 + 1

                    params = {
                        "key": self._google_api_key,
                        "cx": self._search_engine_id,
                        "q": query,
                        "start": start_index,
                        "num": min(10, num_results - len(results)),
                    }

                    response = await client.get(
                        "https://www.googleapis.com/customsearch/v1",
                        params=params,
                    )
                    response.raise_for_status()
                    data = response.json()

                    items = data.get("items", [])
                    for item in items:
                        results.append({
                            "title": item.get("title", ""),
                            "link": item.get("link", ""),
                            "snippet": item.get("snippet", ""),
                        })

                    if len(results) >= num_results:
                        break

            logger.info(f"Google search for '{query}' returned {len(results)} results")
            return results[:num_results]

        except Exception as e:
            logger.error(f"Google search error: {e}")
            # Fallback to DuckDuckGo on error
            logger.info("Falling back to DuckDuckGo")
            return await self._search_duckduckgo(query, num_results)

    async def _search_duckduckgo(
        self,
        query: str,
        num_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search using DuckDuckGo HTML scraping.

        Always uses HTML scraping (httpx) instead of duckduckgo-search library
        to avoid proxy/redirect issues with the library's primp/rquest backend.
        """
        return await self._search_duckduckgo_html(query, num_results)

    async def _search_duckduckgo_html(
        self,
        query: str,
        num_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Fallback DuckDuckGo search using HTML scraping."""
        try:
            import re

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers=headers,
                )
                response.raise_for_status()
                html = response.text

            results = []
            # Simple regex to extract results (fragile, may break)
            result_pattern = r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>'
            snippet_pattern = r'<a[^>]+class="result__snippet"[^>]*>([^<]+)</a>'

            links = re.findall(result_pattern, html)
            snippets = re.findall(snippet_pattern, html)

            for i, (link, title) in enumerate(links[:num_results]):
                snippet = snippets[i] if i < len(snippets) else ""
                results.append({
                    "title": title.strip(),
                    "link": link,
                    "snippet": snippet.strip(),
                })

            logger.info(f"DuckDuckGo HTML search for '{query}' returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"DuckDuckGo HTML search error: {e}")
            return [{"error": f"Search failed: {str(e)}"}]

    def _format_results(self, results: List[Dict[str, Any]]) -> str:
        """Format search results into a readable string for LLM.

        Args:
            results: List of search result dictionaries.

        Returns:
            Formatted string with search results.
        """
        if not results:
            return "No search results found."

        # Check for error
        if len(results) == 1 and "error" in results[0]:
            return f"Search error: {results[0]['error']}"

        output = f"Found {len(results)} search results:\n\n"

        for i, result in enumerate(results, 1):
            title = result.get("title", "No title")
            link = result.get("link", "No URL")
            snippet = result.get("snippet", "No description")

            output += f"{i}. **{title}**\n"
            output += f"   URL: {link}\n"
            output += f"   {snippet}\n\n"

        return output.strip()

    def is_available(self) -> bool:
        """Check if search functionality is available.

        Returns:
            True if either Google API or DuckDuckGo is available.
        """
        return HTTPX_AVAILABLE

    def has_google_api(self) -> bool:
        """Check if Google Custom Search API is configured.

        Returns:
            True if Google API keys are configured.
        """
        return self._has_google_api

    def get_tools(self) -> List[FunctionTool]:
        """Return a list of FunctionTool objects for this toolkit.

        Returns:
            List of FunctionTool objects.
        """
        return [
            FunctionTool(self.search_google),
        ]

    @classmethod
    def toolkit_name(cls) -> str:
        """Return the name of this toolkit."""
        return "Search Toolkit"
