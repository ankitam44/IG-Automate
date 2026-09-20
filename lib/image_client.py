"""Free image generation via pollinations.ai (no API key required).
Quality/reliability is best-effort -- it's a free public service, not an SLA.
For higher quality, swap this module for a paid provider (Ideogram, Stability)
later without touching the agents that call generate_image()."""
import time
import urllib.parse
import urllib.request

BASE_URL = "https://image.pollinations.ai/prompt"


def generate_image(prompt: str, out_path: str, width: int = 1024, height: int = 1350, seed: int | None = None) -> str:
    """Download a generated image to out_path. Returns out_path.
    1024x1350 is Instagram's portrait aspect ratio (4:5)."""
    encoded_prompt = urllib.parse.quote(prompt)
    params = {"width": width, "height": height, "nologo": "true"}
    if seed is not None:
        params["seed"] = seed
    query = urllib.parse.urlencode(params)
    url = f"{BASE_URL}/{encoded_prompt}?{query}"

    last_err = None
    for attempt in range(3):
        try:
            urllib.request.urlretrieve(url, out_path)
            return out_path
        except Exception as e:  # noqa: BLE001 - best-effort free service, just retry
            last_err = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Image generation failed after retries: {last_err}")
