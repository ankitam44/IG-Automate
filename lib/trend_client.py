"""Free, keyless trend signal for the research agent: recent high-point
Hacker News stories mentioning AI/tech keywords, via Algolia's public HN
search API (https://hn.algolia.com/api). No API key, no signup, no rate
limit that this pipeline's weekly cadence could realistically hit.

Best-effort only: trend signal makes the strategy more timely, but a
network hiccup here should never break the research agent, so failures
are swallowed and logged rather than raised."""
import json
import time
import urllib.parse
import urllib.request

SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
KEYWORDS = ["AI", "GPT", "LLM", "OpenAI", "Anthropic", "Gemini", "machine learning"]
LOOKBACK_SECONDS = 7 * 24 * 3600
MIN_POINTS = 15


def get_trending_ai_topics(limit: int = 8) -> list[str]:
    since = int(time.time()) - LOOKBACK_SECONDS
    scored_titles: list[tuple[int, str]] = []
    seen = set()

    for keyword in KEYWORDS:
        params = {
            "query": keyword,
            "tags": "story",
            "numericFilters": f"created_at_i>{since},points>{MIN_POINTS}",
            "hitsPerPage": 20,
        }
        url = f"{SEARCH_URL}?{urllib.parse.urlencode(params)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ig-automate-research-agent"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 - trend signal is a nice-to-have
            print(f"Trend fetch skipped for '{keyword}': {e}")
            continue

        for hit in data.get("hits", []):
            title = (hit.get("title") or "").strip()
            if title and title not in seen:
                seen.add(title)
                scored_titles.append((hit.get("points", 0), title))

    scored_titles.sort(key=lambda t: t[0], reverse=True)
    return [title for _, title in scored_titles[:limit]]
