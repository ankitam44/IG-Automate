"""Thin wrapper around the free-tier Gemini API (Google AI Studio).
Requires GEMINI_API_KEY env var. Free tier limits vary by model -- check
https://ai.google.dev/pricing for current numbers before relying on this at
scale.

Google periodically retires model versions outright (this pipeline broke
once already when gemini-1.5-flash was shut down and every call started
404ing). Rather than hardcode one model string and wait for it to go stale
again, this tries a short list of candidates and uses whichever responds --
set GEMINI_MODEL to pin a specific one instead. Within a candidate, a
transient error (503 busy, 429 rate limited) is retried with backoff before
moving on, since giving up on a real model over a momentary blip would be
worse than the retry cost."""
import json
import os
import time
import urllib.error
import urllib.request

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Ordered by preference; first one that works wins. GEMINI_MODEL, if set, is
# tried first. Confirmed against this project's actual ListModels response
# (not guessed from docs/search, which is how gemini-1.5-flash went stale
# unnoticed) -- includes lite variants since they're generally less
# rate-limited on the free tier than the full flash models.
FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
]

TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES_PER_MODEL = 3
BACKOFF_SECONDS = 2


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


def _call_model_once(model: str, prompt: str, json_mode: bool) -> str:
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


def _call_model(model: str, prompt: str, json_mode: bool) -> str:
    """Retries a single model on transient errors before giving up on it."""
    for attempt in range(1, MAX_RETRIES_PER_MODEL + 1):
        try:
            return _call_model_once(model, prompt, json_mode)
        except urllib.error.HTTPError as e:
            if e.code not in TRANSIENT_STATUS_CODES or attempt == MAX_RETRIES_PER_MODEL:
                raise
            wait = BACKOFF_SECONDS * attempt
            print(f"Gemini model '{model}' returned {e.code} (attempt {attempt}/{MAX_RETRIES_PER_MODEL}), retrying in {wait}s...")
            time.sleep(wait)


def generate(prompt: str, json_mode: bool = False) -> str:
    """Send a single-turn prompt to Gemini and return the text response.
    If json_mode is True, asks the model to respond with raw JSON only."""
    candidates = _candidate_models()
    last_error: Exception | None = None
    for model in candidates:
        try:
            return _call_model(model, prompt, json_mode)
        except urllib.error.HTTPError as e:
            if e.code != 404 and e.code not in TRANSIENT_STATUS_CODES:
                # Something like 400 (bad request) or 401/403 (auth) -- another
                # model won't fix a malformed request or a bad API key, and
                # masking that behind "all candidates failed" would send
                # whoever's debugging this on a pointless chase through
                # models that were never going to work either.
                raise
            print(f"Gemini model '{model}' failed with {e.code}, trying next candidate...")
            last_error = e
            continue
    raise RuntimeError(
        f"All candidate Gemini models failed (tried: {candidates}); "
        f"check https://ai.google.dev/gemini-api/docs/models for current model "
        f"names and set GEMINI_MODEL to override, or Google's status page if "
        f"they're all transiently down."
    ) from last_error


def generate_json(prompt: str) -> dict:
    text = generate(prompt, json_mode=True)
    return json.loads(text)
