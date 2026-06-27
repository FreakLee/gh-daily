"""arXiv recent AI papers (cs.CL / cs.AI / cs.LG), Atom API, free, no key.

arXiv has no engagement metric, so items are scored by recency (newest first).
Use this as the "深度/认知" layer rather than a popularity ranking.
"""

from __future__ import annotations

import logging
import re

import feedparser

from .. import config
from ..models import Item
from .base import http_get

logger = logging.getLogger(__name__)

key = "arxiv"
category = "tech"


def fetch() -> list[Item]:
    query = " OR ".join(f"cat:{c}" for c in config.ARXIV_CATEGORIES)
    response = http_get(
        config.ARXIV_API_URL,
        params={
            "search_query": query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": config.ARXIV_MAX_RESULTS,
        },
        accept="application/atom+xml",
    )
    feed = feedparser.parse(response.text)
    items: list[Item] = []
    total = len(feed.entries)
    for idx, entry in enumerate(feed.entries):
        title = " ".join((entry.get("title") or "").split()).strip()
        url = entry.get("link") or entry.get("id")
        if not title or not url:
            continue
        abstract = " ".join((entry.get("summary") or "").split()).strip()
        primary = entry.get("arxiv_primary_category", {}).get("term", "")
        # Bare arXiv id (strip version), e.g. "2606.27377" — matches HF paper id,
        # so the same paper from HF + arXiv can be de-duplicated in select.py.
        m = re.search(r"(\d{4}\.\d{4,5})", entry.get("id") or url)
        arxiv_id = m.group(1) if m else None

        items.append(
            Item(
                id=url,
                title=title,
                url=url,
                source=key,
                category=category,
                summary_src=abstract,
                score=float(total - idx),   # recency rank
                metric_label="🆕 最新",
                tags=[f"🏷️ {primary}"] if primary else [],
                source_label="arXiv",
                published=entry.get("published"),
                extra={"arxiv_id": arxiv_id} if arxiv_id else {},
            )
        )
    logger.info("arxiv: parsed %d papers", len(items))
    return items
