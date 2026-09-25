"""Thin wrapper around Groq's free-tier API (OpenAI-compatible chat
completions). Requires GROQ_API_KEY env var -- get one free at
https://console.groq.com/keys.

Replaces the earlier Gemini client: Gemini's free tier turned out to have
both a tight per-model quota (5 req/min, 20 req/day) and, separately,
frequent 503 "model overloaded" responses on its free-tier models. Groq
runs its own inference hardware (LPUs) rather than sharing capacity the way
Gemini's free tier does, so it's less prone to that kind of overload."""
import json
import os
import time
import urllib.error
import urllib.request

API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Confirmed against this key's actual /openai/v1/models response, not
# guessed -- Groq's catalog turns over fast (llama-3.3-70b-versatile, an
# earlier default here, is already gone). Override with GROQ_MODEL if this
# one gets deprecated too -- see https://console.groq.com/docs/models, or
# hit /openai/v1/models directly, for the current list.
DEFAULT_MODEL = "openai/gpt-oss-120b"

TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
BACKOFF_SECONDS = 2


def _api_key() -> str:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY environment variable is not set")
    return key


def _model() -> str:
    return os.environ.get("GROQ_MODEL", DEFAULT_MODEL)


def _call_once(prompt: str, json_mode: bool) -> str:
    body = {
        "model": _model(),
        "messages": [{"role": "user", "content": prompt}],
    }
    if json_mode:
        # Groq (like OpenAI) requires the word "JSON" to appear in the
        # prompt when using this mode -- every prompt in this pipeline
        # already asks for JSON output, so that's satisfied.
        body["response_format"] = {"type": "json_object"}

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_api_key()}",
            # Cloudflare (in front of Groq's API) blocks requests with no
            # User-Agent header -- urllib sends none by default, which
            # surfaces as an opaque 403, not anything wrong with the key.
            "User-Agent": "ig-automate/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    try:
        return result["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Groq response shape: {result}") from e


def generate(prompt: str, json_mode: bool = False) -> str:
    """Send a single-turn prompt to Groq and return the text response.
    If json_mode is True, asks the model to respond with raw JSON only.
    Retries a transient error (rate limited, momentarily overloaded) with
    backoff; anything else (bad request, bad key) fails immediately."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return _call_once(prompt, json_mode)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code not in TRANSIENT_STATUS_CODES or attempt == MAX_RETRIES:
                raise RuntimeError(f"Groq API error {e.code}: {body}") from e
            wait = BACKOFF_SECONDS * attempt
            print(f"Groq returned {e.code} (attempt {attempt}/{MAX_RETRIES}), retrying in {wait}s...")
            time.sleep(wait)


def generate_json(prompt: str) -> dict:
    text = generate(prompt, json_mode=True)
    return json.loads(text)
