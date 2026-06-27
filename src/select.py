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


def _content_key(item: Item) -> str:
    """Cross-source identity. The same paper from HF Papers and arXiv shares an
    arXiv id but has different URLs, so key on the arXiv id when present."""
    arxiv_id = item.extra.get("arxiv_id")
    return f"arxiv:{arxiv_id}" if arxiv_id else item.id


def select_for_category(
    items: list[Item],
    quotas: dict[str, int],
    *,
    dedup_against: set[str] | None = None,
) -> list[Item]:
    """Return picks grouped by source, in `quotas` order.

    De-dups across sources by content key (so one paper can't show up twice from
    HF + arXiv) and backfills: if a source's top item was already taken, it falls
    through to that source's next-best instead of losing the slot.
    """
    dedup = dedup_against or set()
    by_source: dict[str, list[Item]] = defaultdict(list)
    for item in items:
        if item.id in dedup:
            continue
        if item.score < config.SOURCE_MIN_SCORE.get(item.source, 0):
            continue
        by_source[item.source].append(item)

    picks: list[Item] = []
    seen: set[str] = set()
    for source, quota in quotas.items():
        ranked = sorted(by_source.get(source, []), key=lambda x: x.score, reverse=True)
        taken = 0
        for item in ranked:
            if taken >= quota:
                break
            key = _content_key(item)
            if key in seen:
                continue
            seen.add(key)
            picks.append(item)
            taken += 1
    return picks


def is_enough(picks: list[Item], *, min_picks: int = config.MIN_PICKS) -> bool:
    return len(picks) >= min_picks
