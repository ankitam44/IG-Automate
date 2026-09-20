"""Pulls Instagram Insights for posts published 48h+ ago that don't yet have
metrics recorded, and feeds a short performance summary back so the next
research_agent run can factor in what actually worked."""
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import instagram_client, store  # noqa: E402

MIN_AGE_HOURS = 48


def main():
    log = store.load("published_log")
    now = datetime.datetime.now(datetime.timezone.utc)
    updated = 0

    for post in log["posts"]:
        if post.get("insights"):
            continue
        published_at = datetime.datetime.fromisoformat(post["published_at"])
        age_hours = (now - published_at).total_seconds() / 3600
        if age_hours < MIN_AGE_HOURS:
            continue

        try:
            data = instagram_client.get_media_insights(post["media_id"])
            post["insights"] = {
                item["name"]: item["values"][0]["value"] for item in data.get("data", [])
            }
            updated += 1
            print(f"Fetched insights for {post['id']}: {post['insights']}")
        except Exception as e:  # noqa: BLE001
            print(f"Could not fetch insights for {post['id']}: {e}")

    if updated:
        store.save("published_log", log)
    else:
        print("No posts due for insight collection yet.")


if __name__ == "__main__":
    main()
