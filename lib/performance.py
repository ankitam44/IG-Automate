"""Turns raw Instagram insights in published_log.json into a performance
summary the research agent can actually reason from, and that the pipeline
can use to make deterministic pause/resume decisions -- not just something
mentioned in a prompt and then ignored."""

MIN_SAMPLES = 3
UNDERPERFORM_RATIO = 0.5


def _engagement_score(insights: dict) -> float:
    return (
        insights.get("likes", 0)
        + insights.get("comments", 0)
        + insights.get("saved", 0) * 2
        + insights.get("shares", 0) * 2
    )


def _summarize(groups: dict) -> dict:
    return {
        key: {
            "avg_engagement": round(sum(scores) / len(scores), 1),
            "sample_size": len(scores),
        }
        for key, scores in groups.items()
    }


def analyze(published_log: dict) -> dict:
    by_pillar: dict[str, list[float]] = {}
    by_format: dict[str, list[float]] = {}

    for post in published_log.get("posts", []):
        insights = post.get("insights")
        if not insights:
            continue
        score = _engagement_score(insights)
        by_pillar.setdefault(post.get("pillar") or "unknown", []).append(score)
        by_format.setdefault(post.get("format") or "unknown", []).append(score)

    pillar_stats = _summarize(by_pillar)
    format_stats = _summarize(by_format)

    all_scores = [s for scores in by_pillar.values() for s in scores]
    overall_avg = round(sum(all_scores) / len(all_scores), 1) if all_scores else None

    def underperformers(stats: dict) -> list[str]:
        if overall_avg is None:
            return []
        return [
            key
            for key, s in stats.items()
            if s["sample_size"] >= MIN_SAMPLES and s["avg_engagement"] < overall_avg * UNDERPERFORM_RATIO
        ]

    top_pillars = sorted(pillar_stats.items(), key=lambda kv: kv[1]["avg_engagement"], reverse=True)

    return {
        "by_pillar": pillar_stats,
        "by_format": format_stats,
        "overall_avg_engagement": overall_avg,
        "sample_size": len(all_scores),
        "underperforming_pillars": underperformers(pillar_stats),
        "underperforming_formats": underperformers(format_stats),
        "top_pillars": [p for p, _ in top_pillars[:3]],
    }
