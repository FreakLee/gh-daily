"""Source registry.

`get_sources(category)` returns one source object per quota key configured for
that category, so commenting out a quota line in config.py also drops the source.
Each source exposes `.key`, `.category`, and `fetch() -> list[Item]`.
"""

from __future__ import annotations

from .. import config
from . import arxiv, github, hackernews, huggingface, rss

# Module-style sources keyed by their config quota key.
_TECH_MODULES = {
    "github": github,
    "hackernews": hackernews,
    "huggingface": huggingface,
    "arxiv": arxiv,
}

_QUOTAS = {
    "tech": config.TECH_SOURCE_QUOTAS,
    "finance": config.FINANCE_SOURCE_QUOTAS,
}


def quotas(category: str) -> dict[str, int]:
    return _QUOTAS[category]


def get_sources(category: str) -> list:
    """Instantiate the sources configured for `category`, in quota order."""
    sources = []
    for key in _QUOTAS[category]:
        if key in _TECH_MODULES:
            sources.append(_TECH_MODULES[key])
        elif key.startswith("rss:"):
            sources.append(rss.make_source(key))
    return sources
