"""Thin wrapper around the free-tier Gemini API (Google AI Studio).
Requires GEMINI_API_KEY env var. Free tier limits vary by model -- check
https://ai.google.dev/pricing for current numbers before relying on this at
scale.

Google periodically retires model versions outright (this pipeline broke
once already when gemini-1.5-flash was shut down and every call started
404ing). Rather than hardcode one model string and wait for it to go stale
again, this tries a short list of candidates and uses whichever responds --
set GEMINI_MODEL to pin a specific one instead."""
import json
import os
import urllib.error
import urllib.request

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Ordered by preference; first one that doesn't 404 wins. GEMINI_MODEL, if
# set, is tried first.
FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-flash-latest"]


def _candidate_models() -> list[str]:
    pinned = os.environ.get("GEMINI_MODEL")
    candidates = ([pinned] if pinned else []) + FALLBACK_MODELS
    seen = set()
    return [m for m in candidates if not (m in seen or seen.add(m))]


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set")
    return key


def _call_model(model: str, prompt: str, json_mode: bool) -> str:
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    if json_mode:
        body["generationConfig"] = {"responseMimeType": "application/json"}

    req = urllib.request.Request(
        f"{API_BASE}/{model}:generateContent?key={_api_key()}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    try:
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Gemini response shape from {model}: {result}") from e


def generate(prompt: str, json_mode: bool = False) -> str:
    """Send a single-turn prompt to Gemini and return the text response.
    If json_mode is True, asks the model to respond with raw JSON only."""
    candidates = _candidate_models()
    last_error: Exception | None = None
    for model in candidates:
        try:
            return _call_model(model, prompt, json_mode)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # This model version doesn't exist (anymore) -- try the next.
                last_error = e
                continue
            raise
    raise RuntimeError(
        f"All candidate Gemini models returned 404 (tried: {candidates}); "
        f"they may all be retired -- check https://ai.google.dev/gemini-api/docs/models "
        f"for current model names and set GEMINI_MODEL to override."
    ) from last_error


def generate_json(prompt: str) -> dict:
    text = generate(prompt, json_mode=True)
    return json.loads(text)
