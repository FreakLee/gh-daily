"""Shared dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RepoMeta:
    full_name: str                  # 'owner/repo'
    url: str
    description: str | None
    language: str | None
    topics: list[str] = field(default_factory=list)
    stars_total: int = 0
    stars_today: int = 0            # delta as reported by trending page (or computed in M2)
    source: str = "trending"        # 'trending' | 'search' | 'both'

    @property
    def owner(self) -> str:
        return self.full_name.split("/", 1)[0]

    @property
    def repo(self) -> str:
        return self.full_name.split("/", 1)[1]


@dataclass
class IssueResult:
    """Outcome of one run."""
    status: str          # 'ok' | 'skip' | 'fail'
    reason: str = ""
    picks: list[RepoMeta] = field(default_factory=list)
    summaries: dict[str, str] = field(default_factory=dict)   # full_name -> summary
