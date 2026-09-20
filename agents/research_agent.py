"""Weekly: synthesize a content strategy from the niche config + any manually
curated competitor reference posts. Writes data/strategy.json."""
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import gemini_client, store  # noqa: E402


def build_prompt(niche: dict, competitors: dict) -> str:
    ref_posts = [
        p for p in competitors.get("reference_posts", [])
        if p.get("hook") or p.get("topic")
    ]
    ref_block = "\n".join(
        f"- @{p['creator']} ({p['format']}): hook=\"{p.get('hook','')}\" "
        f"topic=\"{p.get('topic','')}\" why_it_worked=\"{p.get('why_it_worked','')}\""
        for p in ref_posts
    ) or "(none added yet -- rely on general knowledge of this niche and these creator styles)"

    return f"""You are a social media strategist for an Instagram account in the
niche "{niche['niche']}" ({niche['description']}).
Tone: {niche['tone']}. Audience: {niche['audience']}.

Creators whose style we're inspired by: {', '.join('@' + c for c in niche['seed_creators'])}.

Reference posts we know worked for these creators:
{ref_block}

Content pillars we're considering: {', '.join(niche['content_pillars'])}.

Return ONLY valid JSON with this exact shape:
{{
  "summary": "2-3 sentence strategy summary",
  "recommended_pillars": ["pillar1", "pillar2", ...],
  "recommended_formats": ["carousel", "single_image_quote"],
  "notes": "specific, actionable notes on hooks/captions/visual style that would work well for this account this week"
}}"""


def main():
    niche = store.load_config("niche")
    competitors = store.load("competitor_seed")

    prompt = build_prompt(niche, competitors)
    result = gemini_client.generate_json(prompt)

    result["generated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    store.save("strategy", result)
    print("Strategy updated:")
    print(result["summary"])


if __name__ == "__main__":
    main()
