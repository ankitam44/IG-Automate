"""Weekly: synthesize a content strategy from the niche config, competitor
reference posts (manually curated + a live Apify scrape when configured),
real performance data from past posts, and current AI/tech trend signal.
Writes data/strategy.json.

This is the closed-loop step: analytics_agent records engagement on
published posts, and this agent is what actually reads it back and acts on
it -- pausing pillars/formats that are measurably underperforming rather
than just noting it in a summary nobody enforces."""
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import apify_client, cadence, groq_client, performance, store, trend_client  # noqa: E402


def build_prompt(
    niche: dict, competitors: dict, perf: dict, trends: list[str], live_competitor_posts: list[dict]
) -> str:
    ref_posts = [
        p for p in competitors.get("reference_posts", [])
        if p.get("hook") or p.get("topic")
    ]
    manual_block = "\n".join(
        f"- @{p['creator']} ({p['format']}): hook=\"{p.get('hook','')}\" "
        f"topic=\"{p.get('topic','')}\" why_it_worked=\"{p.get('why_it_worked','')}\""
        for p in ref_posts
    ) or "(none added manually)"

    if live_competitor_posts:
        top_live = sorted(
            live_competitor_posts, key=lambda p: p["likes"] + p["comments"], reverse=True
        )[:10]
        live_block = "\n".join(
            f"- @{p['creator']} ({p['format']}): \"{p['hook']}\" "
            f"({p['likes']} likes, {p['comments']} comments)"
            for p in top_live
        )
    else:
        live_block = "(no live scrape this run -- APIFY_API_TOKEN not set or scrape failed)"

    if perf["sample_size"] == 0:
        perf_block = "(no published post data yet -- this is the first strategy run, rely on general knowledge)"
    else:
        pillar_lines = "\n".join(
            f"  - {pillar}: avg engagement {s['avg_engagement']} across {s['sample_size']} posts"
            for pillar, s in perf["by_pillar"].items()
        )
        format_lines = "\n".join(
            f"  - {fmt}: avg engagement {s['avg_engagement']} across {s['sample_size']} posts"
            for fmt, s in perf["by_format"].items()
        )
        perf_block = f"""Overall average engagement score: {perf['overall_avg_engagement']} ({perf['sample_size']} scored posts)
By pillar:
{pillar_lines}
By format:
{format_lines}
Top performing pillars so far: {', '.join(perf['top_pillars']) or 'not enough data'}
Engagement trend (recent posts vs older posts): {perf['engagement_trend'] or 'not enough data yet'}
Note: pillars/formats with enough samples and well below-average engagement will be
automatically paused by the pipeline regardless of what you recommend here, so lean
into what's working rather than trying to rescue a clear underperformer. Posting
cadence is also adjusted automatically from this same trend -- mention it in your
summary if it changed, but don't recommend a cadence change yourself."""

    trend_block = (
        "\n".join(f"- {t}" for t in trends)
        if trends
        else "(no trend signal this run -- rely on general knowledge of what's currently buzzy in AI/tech)"
    )

    return f"""You are a social media strategist for an Instagram account in the
niche "{niche['niche']}" ({niche['description']}).
Tone: {niche['tone']}. Audience: {niche['audience']}.

Creators whose style we're inspired by: {', '.join('@' + c for c in niche['seed_creators'])}.

Manually curated reference posts (added by hand, includes why they worked):
{manual_block}

Live-scraped recent posts from these creators this week (Apify, sorted by
engagement, no "why it worked" -- infer that yourself from the caption and
the numbers):
{live_block}

Our own post performance so far:
{perf_block}

Recent trending AI/tech headlines (Hacker News, last 7 days, use only what fits
the account's fun/low-jargon tone -- most of these are too technical to use
directly, pick the ones with a relatable hook):
{trend_block}

Content pillars we're considering: {', '.join(niche['content_pillars'])}.

Return ONLY valid JSON with this exact shape:
{{
  "summary": "2-3 sentence strategy summary that references what's actually working if we have data",
  "recommended_pillars": ["pillar1", "pillar2", ...],
  "recommended_formats": ["carousel", "single_image_quote"],
  "notes": "specific, actionable notes on hooks/captions/visual style that would work well for this account this week, referencing trending topics or performance data where relevant"
}}"""


def apply_performance_decisions(result: dict, niche: dict, perf: dict) -> list[str]:
    """Deterministically enforces pause decisions in code rather than trusting
    the LLM to have honored the prompt's instruction. Returns a human-readable
    decision log for transparency."""
    decisions = []

    def filter_and_log(key: str, fallback: list[str], underperforming: list[str], stats_by_key: dict):
        chosen = result.get(key) or fallback
        kept = [item for item in chosen if item not in underperforming]
        if not kept:
            # Never leave ourselves with nothing to post -- an empty queue is
            # worse than temporarily keeping a weak performer alive.
            decisions.append(
                f"All candidate {key} are underperforming by the current threshold; "
                "keeping them anyway rather than generating zero content."
            )
            return chosen
        for item in underperforming:
            if item in chosen and item not in kept:
                s = stats_by_key[item]
                decisions.append(
                    f"Paused '{item}' ({key}): avg engagement {s['avg_engagement']} over "
                    f"{s['sample_size']} posts, vs overall avg {perf['overall_avg_engagement']}."
                )
        return kept

    result["recommended_pillars"] = filter_and_log(
        "recommended_pillars", niche["content_pillars"], perf["underperforming_pillars"], perf["by_pillar"]
    )
    result["recommended_formats"] = filter_and_log(
        "recommended_formats", niche["post_formats"], perf["underperforming_formats"], perf["by_format"]
    )
    return decisions


def main():
    niche = store.load_config("niche")
    competitors = store.load("competitor_seed")
    published_log = store.load("published_log")

    perf = performance.analyze(published_log)
    trends = trend_client.get_trending_ai_topics()
    live_competitor_posts = apify_client.fetch_competitor_reference_posts(niche["seed_creators"])
    if live_competitor_posts:
        print(f"Fetched {len(live_competitor_posts)} live competitor posts via Apify")

    prompt = build_prompt(niche, competitors, perf, trends, live_competitor_posts)
    result = groq_client.generate_json(prompt)

    decision_log = apply_performance_decisions(result, niche, perf)

    new_cadence, cadence_decision = cadence.adjust_for_trend(niche["posting_cadence"], perf["engagement_trend"])
    if cadence_decision:
        niche["posting_cadence"] = new_cadence
        store.save_config("niche", niche)
        decision_log.append(cadence_decision)

    result["paused_pillars"] = perf["underperforming_pillars"]
    result["paused_formats"] = perf["underperforming_formats"]
    result["performance_snapshot"] = perf
    result["trending_topics_used"] = trends
    result["decision_log"] = decision_log
    result["generated_at"] = datetime.datetime.utcnow().isoformat() + "Z"

    store.save("strategy", result)
    print("Strategy updated:")
    print(result["summary"])
    if decision_log:
        print("Autonomous decisions this run:")
        for d in decision_log:
            print(f"  - {d}")


if __name__ == "__main__":
    main()
