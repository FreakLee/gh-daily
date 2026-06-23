"""Per-source quota selection.

Heat from different sources isn't comparable (GitHub stars vs HN points vs
recency), so we never sort globally. Each source fills a fixed number of slots,
ranked only within itself. Items already published recently (history dedup) and
items below a source's `SOURCE_MIN_SCORE` floor are dropped first.
"""

from __future__ import annotations

from collections import defaultdict

from . import config
from .models import Item


def select_for_category(
    items: list[Item],
    quotas: dict[str, int],
    *,
    dedup_against: set[str] | None = None,
) -> list[Item]:
    """Return picks grouped by source, in `quotas` order."""
    dedup = dedup_against or set()
    by_source: dict[str, list[Item]] = defaultdict(list)
    for item in items:
        if item.id in dedup:
            continue
        if item.score < config.SOURCE_MIN_SCORE.get(item.source, 0):
            continue
        by_source[item.source].append(item)

    picks: list[Item] = []
    for source, quota in quotas.items():
        ranked = sorted(by_source.get(source, []), key=lambda x: x.score, reverse=True)
        picks.extend(ranked[:quota])
    return picks


def is_enough(picks: list[Item], *, min_picks: int = config.MIN_PICKS) -> bool:
    return len(picks) >= min_picks
