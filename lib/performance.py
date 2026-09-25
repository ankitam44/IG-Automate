"""Turns raw Instagram insights in published_log.json into a performance
summary the research agent can actually reason from, and that the pipeline
can use to make deterministic pause/resume decisions -- not just something
mentioned in a prompt and then ignored."""

MIN_SAMPLES = 3
UNDERPERFORM_RATIO = 0.5

MIN_TREND_SAMPLES = 6
TREND_CHANGE_RATIO = 0.15


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


def _engagement_trend(posts: list[dict]) -> str | None:
    """Compares recent posts to older posts to detect a real direction, not
    noise. Needs MIN_TREND_SAMPLES posts with both a timestamp and insights;
    below that, returns None (no opinion) rather than guessing from too few
    data points."""
    scored = [
        (p["published_at"], _engagement_score(p["insights"]))
        for p in posts
        if p.get("insights") and p.get("published_at")
    ]
    if len(scored) < MIN_TREND_SAMPLES:
        return None

    scored.sort(key=lambda t: t[0])
    midpoint = len(scored) // 2
    older_scores = [s for _, s in scored[:midpoint]]
    recent_scores = [s for _, s in scored[midpoint:]]
    older_avg = sum(older_scores) / len(older_scores)
    recent_avg = sum(recent_scores) / len(recent_scores)

    if older_avg == 0:
        return "improving" if recent_avg > 0 else None
    change = (recent_avg - older_avg) / older_avg
    if change >= TREND_CHANGE_RATIO:
        return "improving"
    if change <= -TREND_CHANGE_RATIO:
        return "declining"
    return "flat"


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
        "engagement_trend": _engagement_trend(published_log.get("posts", [])),
    }
