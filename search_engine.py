"""Pluggable search engine with multiple backend support."""

import sys
from dataclasses import dataclass, field
from typing import Optional

from config import SearchConfig, TRUSTED_SOURCES


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source_name: str = ""
    is_gov: bool = False
    is_authoritative: bool = False


def _classify_source(url: str) -> tuple[str, bool, bool]:
    """Classify a URL by source type using config domain lists."""
    from urllib.parse import urlparse
    from config import PARAGUAY_GOV_DOMAINS, ALLOWED_NEWS_DOMAINS
    domain = urlparse(url).netloc.lower()
    is_gov = any(d in domain for d in PARAGUAY_GOV_DOMAINS)
    is_auth = is_gov or any(d in domain for d in ALLOWED_NEWS_DOMAINS)
    return domain, is_gov, is_auth


def search_duckduckgo(query: str, max_results: int = 10, timelimit: str = None) -> list[SearchResult]:
    """Search using DuckDuckGo (free, no API key).

    timelimit: 'd' (day), 'w' (week), 'm' (month), 'y' (year)
    """
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            print("[ERROR] ddgs not installed. Run: pip install ddgs")
            return []

    results = []
    try:
        with DDGS() as ddgs:
            kwargs = {"max_results": max_results}
            if timelimit:
                kwargs["timelimit"] = timelimit
            for r in ddgs.text(query, **kwargs):
                source, is_gov, is_auth = _classify_source(r.get("href", ""))
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", ""),
                    snippet=r.get("body", ""),
                    source_name=source,
                    is_gov=is_gov,
                    is_authoritative=is_auth,
                ))
    except Exception as e:
        print(f"[WARN] DuckDuckGo search error: {e}")

    return results


def search_brave(query: str, api_key: str, max_results: int = 10) -> list[SearchResult]:
    """Search using Brave Search API."""
    import requests
    results = []
    try:
        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"Accept": "application/json", "Accept-Encoding": "gzip",
                      "X-Subscription-Token": api_key},
            params={"q": query, "count": min(max_results, 20)},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        for r in data.get("web", {}).get("results", []):
            source, is_gov, is_auth = _classify_source(r.get("url", ""))
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("description", ""),
                source_name=source,
                is_gov=is_gov,
                is_authoritative=is_auth,
            ))
    except Exception as e:
        print(f"[WARN] Brave search error: {e}")
    return results


def search_manual(prompt: str) -> list[SearchResult]:
    """Manual input mode: user pastes research notes."""
    print(f"\n{'='*60}")
    print(f"请在浏览器中搜索以下关键词，然后将相关新闻的标题和链接粘贴到此处：")
    print(f"  {prompt}")
    print(f"每行一条：标题 | URL | 摘要")
    print(f"输入空行结束。")
    print(f"{'='*60}\n")

    results = []
    while True:
        line = input("> ").strip()
        if not line:
            break
        parts = line.split("|")
        if len(parts) >= 2:
            source, is_gov, is_auth = _classify_source(parts[1].strip())
            results.append(SearchResult(
                title=parts[0].strip(),
                url=parts[1].strip(),
                snippet=parts[2].strip() if len(parts) > 2 else "",
                source_name=source,
                is_gov=is_gov,
                is_authoritative=is_auth,
            ))
    return results


class SearchEngine:
    """Unified search interface with pluggable backends."""

    def __init__(self, config: SearchConfig):
        self.config = config
        self.all_results: list[SearchResult] = []

    def search(self, queries: list[str]) -> list[SearchResult]:
        """Run searches for multiple queries and return aggregated results."""
        self.all_results = []

        for query in queries:
            if self.config.backend == "brave" and self.config.brave_api_key:
                results = search_brave(query, self.config.brave_api_key,
                                        self.config.max_results_per_query)
            elif self.config.backend == "serpapi":
                print("[INFO] SerpAPI backend: please configure in search_engine.py")
                results = []
            elif self.config.backend == "newsapi":
                print("[INFO] NewsAPI backend: please configure in search_engine.py")
                results = []
            elif self.config.backend == "manual":
                results = search_manual(query)
            else:
                results = search_duckduckgo(query, self.config.max_results_per_query)

            self.all_results.extend(results)

        # Deduplicate by URL
        seen = set()
        deduped = []
        for r in self.all_results:
            if r.url not in seen:
                seen.add(r.url)
                deduped.append(r)
        self.all_results = deduped

        return self.all_results

    def get_authoritative(self) -> list[SearchResult]:
        """Return only results from authoritative sources."""
        return [r for r in self.all_results if r.is_authoritative]

    def get_gov_sources(self) -> list[SearchResult]:
        """Return only government sources."""
        return [r for r in self.all_results if r.is_gov]
