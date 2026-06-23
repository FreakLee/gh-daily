"""Shared dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Item:
    """A generic content entry from any source (GitHub repo, HN post, paper,
    finance article, central-bank release, ...).

    Sources normalize their native payload into this shape so that selection,
    summarization and rendering stay source-agnostic.
    """

    id: str                          # stable dedup key (usually the URL)
    title: str                       # headline shown in the digest
    url: str
    source: str                      # "github" | "hackernews" | "arxiv" | "huggingface" | "rss:<feed>"
    category: str                    # "tech" | "finance"
    summary_src: str | None = None   # original blurb/abstract (may be English)
    score: float = 0.0               # heat for ranking *within* a source
    metric_label: str = ""           # primary chip, e.g. "📈 +1.2k ⭐" / "🔺 480 分"
    tags: list[str] = field(default_factory=list)   # extra chips, e.g. ["🔧 Rust", "🏷️ cli"]
    source_label: str = ""           # human source name shown per item, e.g. "GitHub" / "华尔街见闻"
    published: str | None = None     # ISO timestamp when known
    translate_title: bool = False    # if True, summarizer also produces a Chinese title
    extra: dict = field(default_factory=dict)       # source-specific fields
    ai_summary: str | None = None    # filled by the summarizer
    title_zh: str | None = None      # filled by the summarizer when translate_title

    @property
    def display_summary(self) -> str:
        return self.ai_summary or self.summary_src or ""

    @property
    def display_title(self) -> str:
        return self.title_zh or self.title


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
