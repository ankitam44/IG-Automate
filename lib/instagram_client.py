"""Instagram Graph API client (free, official Meta API).
Requires an Instagram Business/Creator account linked to a Facebook Page.
Env vars required:
  IG_BUSINESS_ACCOUNT_ID - the IG user id (not username)
  IG_ACCESS_TOKEN        - a long-lived Page access token with
                            instagram_content_publish permission

Note: Graph API requires publicly reachable image URLs, not file uploads.
This repo's publisher pushes generated images to the repo itself and uses
the raw.githubusercontent.com URL (repo must be public) as free hosting.
"""
import json
import os
import time
import urllib.parse
import urllib.request

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


def _env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"{name} environment variable is not set")
    return val


def _post(path: str, params: dict) -> dict:
    url = f"{GRAPH_API_BASE}/{path}"
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(path: str, params: dict) -> dict:
    url = f"{GRAPH_API_BASE}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def create_image_container(image_url: str, caption: str) -> str:
    ig_user_id = _env("IG_BUSINESS_ACCOUNT_ID")
    token = _env("IG_ACCESS_TOKEN")
    result = _post(
        f"{ig_user_id}/media",
        {"image_url": image_url, "caption": caption, "access_token": token},
    )
    if "id" not in result:
        raise RuntimeError(f"Failed to create media container: {result}")
    return result["id"]


def create_carousel_container(image_urls: list[str], caption: str) -> str:
    ig_user_id = _env("IG_BUSINESS_ACCOUNT_ID")
    token = _env("IG_ACCESS_TOKEN")
    child_ids = []
    for url in image_urls:
        child = _post(
            f"{ig_user_id}/media",
            {"image_url": url, "is_carousel_item": "true", "access_token": token},
        )
        if "id" not in child:
            raise RuntimeError(f"Failed to create carousel item: {child}")
        child_ids.append(child["id"])

    result = _post(
        f"{ig_user_id}/media",
        {
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
            "access_token": token,
        },
    )
    if "id" not in result:
        raise RuntimeError(f"Failed to create carousel container: {result}")
    return result["id"]


def publish_container(container_id: str) -> str:
    ig_user_id = _env("IG_BUSINESS_ACCOUNT_ID")
    token = _env("IG_ACCESS_TOKEN")
    # Container needs a moment to finish processing before publish.
    time.sleep(10)
    result = _post(
        f"{ig_user_id}/media_publish",
        {"creation_id": container_id, "access_token": token},
    )
    if "id" not in result:
        raise RuntimeError(f"Failed to publish container: {result}")
    return result["id"]


def get_media_insights(media_id: str) -> dict:
    token = _env("IG_ACCESS_TOKEN")
    return _get(
        f"{media_id}/insights",
        {"metric": "impressions,reach,likes,comments,saved,shares", "access_token": token},
    )
