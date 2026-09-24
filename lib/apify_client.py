"""Thin wrapper around Apify's REST API for running the Instagram post
scraper actor. Requires APIFY_API_TOKEN env var -- get one free at
https://console.apify.com/settings/integrations (new accounts get monthly
free usage credit, which comfortably covers a light weekly scrape of a
handful of profiles, but this is metered, not unlimited like the Groq key).

Scraping Instagram via a third party like this sits in the same gray area
every "competitor research" tool in this space operates in -- Instagram's
ToS technically prohibits it. This fetches a small number of public posts
from a handful of accounts once a week, not bulk harvesting, but it's worth
knowing that going in.

Best-effort, same pattern as lib/trend_client.py: a scrape failure (missing
token, actor error, one broken profile) should never break the research
agent -- it falls back to the manually curated competitor_seed.json."""
import json
import os
import urllib.error
import urllib.request

API_BASE = "https://api.apify.com/v2"

# Official Apify Instagram scraper actor. Override with APIFY_ACTOR_ID if
# this ever gets renamed/replaced -- see https://apify.com/apify/instagram-scraper
ACTOR_ID = os.environ.get("APIFY_ACTOR_ID", "apify~instagram-scraper")

DEFAULT_RESULTS_PER_CREATOR = 5
TIMEOUT_SECONDS = 90


def _api_token() -> str:
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        raise RuntimeError("APIFY_API_TOKEN environment variable is not set")
    return token


def _fetch_recent_posts(username: str, limit: int) -> list[dict]:
    """Runs the scraper synchronously for one profile and returns raw post
    items in whatever shape the actor emits (caption, likesCount, etc)."""
    body = {
        "directUrls": [f"https://www.instagram.com/{username}/"],
        "resultsType": "posts",
        "resultsLimit": limit,
    }
    url = f"{API_BASE}/acts/{ACTOR_ID}/run-sync-get-dataset-items?token={_api_token()}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "ig-automate/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _normalize(username: str, item: dict) -> dict:
    caption = (item.get("caption") or "").strip()
    media_type = item.get("type") or ""
    return {
        "creator": username,
        "format": "carousel" if media_type == "Sidecar" else "single_image_quote",
        "hook": caption.splitlines()[0][:140] if caption else "",
        "topic": caption[:280],
        "likes": item.get("likesCount") or 0,
        "comments": item.get("commentsCount") or 0,
        "url": item.get("url") or "",
    }


def fetch_competitor_reference_posts(
    usernames: list[str], per_creator: int = DEFAULT_RESULTS_PER_CREATOR
) -> list[dict]:
    """Best-effort live scrape of recent posts for each seed creator.
    Returns [] (never raises) if APIFY_API_TOKEN isn't set or every scrape
    fails -- callers should treat this as a supplement to, not a
    replacement for, the manually curated competitor_seed.json."""
    if not os.environ.get("APIFY_API_TOKEN"):
        print("APIFY_API_TOKEN not set -- skipping live competitor scrape, using manual seed data only.")
        return []

    posts = []
    for username in usernames:
        try:
            items = _fetch_recent_posts(username, per_creator)
        except Exception as e:  # noqa: BLE001 - one broken profile shouldn't kill the run
            print(f"Apify scrape skipped for @{username}: {e}")
            continue
        posts.extend(_normalize(username, item) for item in items)

    return posts
