"""Thin wrapper around the free-tier Gemini API (Google AI Studio).
Requires GEMINI_API_KEY env var. Free tier: ~15 req/min, 1M tokens/day
on gemini-1.5-flash as of this writing -- check https://ai.google.dev/pricing
for current limits before relying on this at scale."""
import json
import os
import urllib.request

MODEL = "gemini-1.5-flash"
API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
)


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set")
    return key


def generate(prompt: str, json_mode: bool = False) -> str:
    """Send a single-turn prompt to Gemini and return the text response.
    If json_mode is True, asks the model to respond with raw JSON only."""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
    }
    if json_mode:
        body["generationConfig"] = {"responseMimeType": "application/json"}

    req = urllib.request.Request(
        f"{API_URL}?key={_api_key()}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    try:
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Gemini response shape: {result}") from e


def generate_json(prompt: str) -> dict:
    text = generate(prompt, json_mode=True)
    return json.loads(text)
