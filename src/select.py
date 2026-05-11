"""Pick the day's repos: sort by today's star delta, threshold, top-N."""

from __future__ import annotations

from . import config
from .models import RepoMeta


def select_picks(
    candidates: list[RepoMeta],
    *,
    min_delta: int = config.MIN_DELTA_THRESHOLD,
    max_picks: int = config.MAX_PICKS,
    dedup_against: set[str] | None = None,
) -> list[RepoMeta]:
    """Return up to `max_picks` repos sorted by `stars_today` desc.

    `dedup_against` is a set of `full_name` strings already published recently;
    they are excluded. M1 passes None (no history yet).
    """
    dedup = dedup_against or set()

    eligible = [
        repo for repo in candidates
        if repo.stars_today >= min_delta and repo.full_name not in dedup
    ]
    eligible.sort(key=lambda r: r.stars_today, reverse=True)
    return eligible[:max_picks]


def is_enough(picks: list[RepoMeta], *, min_picks: int = config.MIN_PICKS) -> bool:
    return len(picks) >= min_picks
