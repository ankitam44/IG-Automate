"""Adjusts posting frequency based on real engagement trend. Deliberately
conservative: moves one rung on a fixed ladder per research_agent run (at
most weekly), never below 1x/week or above 5x/week, and only when there's
a real trend (see performance.MIN_TREND_SAMPLES / TREND_CHANGE_RATIO) --
never on noise from a handful of posts."""

CADENCE_LADDER = [
    ["Wed"],
    ["Mon", "Thu"],
    ["Mon", "Wed", "Fri"],
    ["Mon", "Wed", "Fri", "Sat"],
    ["Mon", "Tue", "Wed", "Thu", "Fri"],
]


def _current_rung(days: list[str]) -> int:
    count = len(days)
    return min(max(count - 1, 0), len(CADENCE_LADDER) - 1)


def adjust_for_trend(cadence: dict, trend: str | None) -> tuple[dict, str | None]:
    """Returns (possibly updated cadence dict, decision log line or None)."""
    if trend not in ("improving", "declining"):
        return cadence, None

    days = cadence.get("days", [])
    rung = _current_rung(days)

    if trend == "improving" and rung < len(CADENCE_LADDER) - 1:
        new_rung = rung + 1
    elif trend == "declining" and rung > 0:
        new_rung = rung - 1
    else:
        return cadence, None

    new_days = CADENCE_LADDER[new_rung]
    if set(new_days) == set(days):
        return cadence, None

    new_cadence = {**cadence, "days": new_days}
    decision = (
        f"Engagement trend '{trend}' across recent posts -> posting cadence "
        f"changed from {len(days)}x/week ({', '.join(days)}) to "
        f"{len(new_days)}x/week ({', '.join(new_days)})."
    )
    return new_cadence, decision
