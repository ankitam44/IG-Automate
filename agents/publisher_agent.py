"""Publishes any due, ready posts from the queue to Instagram via the Graph
API, then moves them into published_log.json. Requires the repo to be
public (image files are served as raw.githubusercontent.com URLs, which is
what the Graph API needs -- it won't accept local file uploads)."""
import datetime
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import instagram_client, store  # noqa: E402

BRANCH = os.environ.get("GIT_BRANCH", "main")


def raw_url(repo: str, rel_path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{BRANCH}/{rel_path}"


def main():
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise RuntimeError(
            "GITHUB_REPOSITORY env var not set (expected 'owner/repo'); "
            "needed to build public image URLs for the Graph API."
        )

    queue = store.load("queue")
    log = store.load("published_log")
    now = datetime.datetime.now(datetime.timezone.utc)

    remaining = []
    for post in queue["posts"]:
        scheduled_for = datetime.datetime.fromisoformat(post["scheduled_for"])
        due = scheduled_for.astimezone(datetime.timezone.utc) <= now
        if post["status"] != "ready" or not due:
            remaining.append(post)
            continue

        image_urls = [raw_url(repo, p) for p in post["image_paths"]]
        try:
            if post["format"] == "carousel" and len(image_urls) > 1:
                container_id = instagram_client.create_carousel_container(image_urls, post["caption"])
            else:
                container_id = instagram_client.create_image_container(image_urls[0], post["caption"])
            media_id = instagram_client.publish_container(container_id)
        except Exception as e:  # noqa: BLE001
            print(f"Failed to publish post {post['id']}: {e}")
            post["status"] = "failed"
            post["error"] = str(e)
            remaining.append(post)
            continue

        post["status"] = "published"
        post["media_id"] = media_id
        post["published_at"] = now.isoformat()
        log["posts"].append(post)
        print(f"Published post {post['id']} -> media_id {media_id}")

    queue["posts"] = remaining
    store.save("queue", queue)
    store.save("published_log", log)


if __name__ == "__main__":
    main()
