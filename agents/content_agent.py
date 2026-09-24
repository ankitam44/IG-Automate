"""Generates new post concepts (caption + hashtags + image prompts), renders
images via the free image client, and appends ready-to-publish entries to
data/queue.json. Run on a cadence (e.g. twice a week) to keep the queue full."""
import datetime
import os
import sys
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import gemini_client, image_client, store  # noqa: E402

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

Return ONLY valid JSON: a list of {n} objects, each with this exact shape:
{{
  "format": "carousel" or "single_image_quote",
  "pillar": "which content pillar this uses",
  "caption": "the full Instagram caption, engaging, includes a hook in the first line",
  "hashtags": ["#tag1", "#tag2", ... 8-12 relevant hashtags],
  "image_prompts": ["a vivid, detailed prompt for an AI image generator describing one visual slide"],
  "slide_count": 1
}}

For "carousel" format, provide 3-5 image_prompts (one per slide, visually consistent style,
minimal text overlay described in the prompt) and set slide_count to match.
For "single_image_quote" format, provide exactly 1 image_prompt and slide_count 1.
Keep image prompts simple, bright, flat-illustration or clean-graphic style (not photorealistic),
since these will be rendered by a free image generator."""


def main():
    niche = store.load_config("niche")
    strategy = store.load("strategy")
    queue = store.load("queue")

    prompt = build_concept_prompt(niche, strategy, POSTS_TO_GENERATE)
    concepts = gemini_client.generate_json(prompt)
    if isinstance(concepts, dict):
        concepts = concepts.get("posts") or concepts.get("concepts") or [concepts]

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    slots = next_slots(niche, len(concepts), already_queued=len(queue["posts"]))

    for concept, scheduled_for in zip(concepts, slots):
        post_id = uuid.uuid4().hex[:10]
        image_paths = []
        for i, img_prompt in enumerate(concept["image_prompts"]):
            rel_path = f"data/generated/images/{post_id}_{i}.jpg"
            abs_path = Path(__file__).resolve().parent.parent / rel_path
            image_client.generate_image(img_prompt, str(abs_path))
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
        print(f"Queued post {post_id} ({concept['format']}) for {scheduled_for}")

    store.save("queue", queue)


if __name__ == "__main__":
    main()
