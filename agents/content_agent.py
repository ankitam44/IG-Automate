"""Generates new post concepts (caption + hashtags + structured slide
content), renders slides as HTML/CSS templates via a headless browser, and
appends ready-to-publish entries to data/queue.json. Run on a cadence
(e.g. twice a week) to keep the queue full.

Slides are rendered from structured content (headline, bullets, bar values
-- see lib/render_client.py's four templates), not from natural-language
prompts to an image diffusion model. This account's actual inspiration
posts are bold typography/card graphic design, not photos, and a diffusion
model reliably produces garbled text and generic stock-photo compositions
for that kind of content -- a real browser rendering real text doesn't."""
import datetime
import os
import sys
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import groq_client, render_client, store  # noqa: E402

IMAGES_DIR = Path(__file__).resolve().parent.parent / "data" / "generated" / "images"
POSTS_TO_GENERATE = int(os.environ.get("POSTS_TO_GENERATE", "2"))


def next_slots(niche: dict, count: int, already_queued: int) -> list[str]:
    cadence = niche["posting_cadence"]
    tz = ZoneInfo(cadence["timezone"])
    hour, minute = map(int, cadence["time_local"].split(":"))
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    target_days = {day_names.index(d) for d in cadence["days"]}

    slots = []
    cursor = datetime.datetime.now(tz).replace(hour=hour, minute=minute, second=0, microsecond=0)
    skipped = 0
    while len(slots) < count:
        if cursor.weekday() in target_days and cursor > datetime.datetime.now(tz):
            if skipped >= already_queued:
                slots.append(cursor.isoformat())
            skipped += 1
        cursor += datetime.timedelta(days=1)
    return slots


def active_pillars(niche: dict, strategy: dict) -> list[str]:
    """Filters out whatever research_agent paused for underperformance. Defends
    against stale/hand-edited strategy.json still listing a paused pillar."""
    candidates = strategy.get("recommended_pillars") or niche["content_pillars"]
    paused = set(strategy.get("paused_pillars", []))
    filtered = [p for p in candidates if p not in paused]
    return filtered or candidates


def active_formats(niche: dict, strategy: dict) -> list[str]:
    candidates = strategy.get("recommended_formats") or niche["post_formats"]
    paused = set(strategy.get("paused_formats", []))
    filtered = [f for f in candidates if f not in paused]
    return filtered or candidates


def build_concept_prompt(niche: dict, strategy: dict, n: int) -> str:
    pillars = active_pillars(niche, strategy)
    formats = active_formats(niche, strategy)
    trends = strategy.get("trending_topics_used") or []
    trend_block = (
        "\n".join(f"- {t}" for t in trends)
        if trends
        else "(no trend signal available -- skip topical references)"
    )
    return f"""You are creating {n} Instagram post concepts for an account about
"{niche['niche']}" ({niche['description']}). Tone: {niche['tone']}.
Audience: {niche['audience']}.

Strategy notes: {strategy.get('notes', '')}
Content pillars to draw from: {', '.join(pillars)}
Formats available: {', '.join(formats)}

Recent trending AI/tech headlines you can riff on for relatability (optional,
only use one if it genuinely fits the fun/low-jargon tone -- don't force it):
{trend_block}

Each slide is rendered from structured content into a bold, typography-driven
card graphic (like a Canva-style carousel post) -- NOT a photo, so never
describe a photo or illustration. Each slide must use one of these four
templates:

Every template except "list" can take an optional "highlight" field: a
SHORT phrase (2-4 words) that must be an EXACT substring of that template's
headline/title, which gets rendered with a marker-highlighter effect. Only
include it if you can quote the exact substring -- an approximate or
paraphrased "highlight" won't match and will be silently ignored.

- "hook": a big bold statement. Fields: headline (<=70 chars), highlight
  (optional, exact substring of headline), subtext (optional, <=90 chars),
  badge (optional, <=18 chars, a short punchy label like "SAVE THIS"). Good
  for hooks, myths, relatable moments.
- "spotlight": headline + description + a highlighted info card. Fields:
  headline (<=70 chars), highlight (optional, exact substring of headline),
  description (<=110 chars), card_title (<=30 chars), card_body (<=110
  chars), pills (optional list of 2-4 short tags like "FREE"). Good for "AI
  tool of the day".
- "list": a title plus 2-4 small cards. Fields: title (<=60 chars), items
  (list of {{"label": "<=30 chars", "bullets": ["<=45 chars", ...max 2]}}).
  Good for tutorials/steps/roundups.
- "bars": a title plus labeled comparison meters. Fields: title (<=60
  chars), highlight (optional, exact substring of title), bars (list of
  {{"label": "<=20 chars", "value": 0-100}}, 2-3 items), caption (optional,
  <=90 chars). Good for before/after or X vs Y.

Return ONLY valid JSON: a single JSON object with one key, "posts", whose
value is a list of exactly {n} post objects, each with this exact shape:
{{
  "posts": [
    {{
      "format": "carousel" or "single_image_quote",
      "pillar": "which content pillar this uses",
      "caption": "the full Instagram caption, engaging, includes a hook in the first line",
      "hashtags": ["#tag1", "#tag2", ... 8-12 relevant hashtags],
      "slides": [
        {{"template": "hook", "eyebrow": "optional short all-caps label", ...template fields...}}
      ]
    }}
  ]
}}

For "carousel" format, provide 3-5 slides (mix templates for visual variety
across the carousel). For "single_image_quote" format, provide exactly 1
slide, usually "hook"."""


def _build_slide(concept: dict, slide_spec: dict, index: int, total: int) -> dict:
    """Fills in index/total/eyebrow deterministically in code rather than
    trusting the model to keep them consistent across a multi-slide post."""
    merged = dict(slide_spec)
    merged["index"] = index
    merged["total"] = total
    if not merged.get("eyebrow") and total > 1:
        merged["eyebrow"] = concept.get("pillar", "").upper()
    return merged


def main():
    niche = store.load_config("niche")
    strategy = store.load("strategy")
    queue = store.load("queue")

    prompt = build_concept_prompt(niche, strategy, POSTS_TO_GENERATE)
    concepts = groq_client.generate_json(prompt)
    if isinstance(concepts, dict):
        concepts = concepts.get("posts") or concepts.get("concepts") or [concepts]

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    slots = next_slots(niche, len(concepts), already_queued=len(queue["posts"]))

    with render_client.Renderer() as renderer:
        for concept, scheduled_for in zip(concepts, slots):
            post_id = uuid.uuid4().hex[:10]
            look = render_client.look_for(post_id)
            slide_specs = concept.get("slides") or []
            total = len(slide_specs)

            image_paths = []
            for i, slide_spec in enumerate(slide_specs):
                slide = _build_slide(concept, slide_spec, i + 1, total)
                rel_path = f"data/generated/images/{post_id}_{i}.png"
                abs_path = Path(__file__).resolve().parent.parent / rel_path
                renderer.render(slide, look, str(abs_path))
                image_paths.append(rel_path)

            queue["posts"].append({
                "id": post_id,
                "status": "ready",
                "format": concept["format"],
                "pillar": concept.get("pillar", ""),
                "caption": concept["caption"] + "\n\n" + " ".join(concept["hashtags"]),
                "image_paths": image_paths,
                "scheduled_for": scheduled_for,
                "created_at": datetime.datetime.utcnow().isoformat() + "Z",
            })
            print(f"Queued post {post_id} ({concept['format']}, {total} slides) for {scheduled_for}")

    store.save("queue", queue)


if __name__ == "__main__":
    main()
