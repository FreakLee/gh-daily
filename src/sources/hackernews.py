"""Hacker News front page via the Algolia API (free, no key)."""

from __future__ import annotations

import logging

from .. import config
from ..models import Item
from .base import fmt_int, http_get

logger = logging.getLogger(__name__)

key = "hackernews"
category = "tech"


def fetch() -> list[Item]:
    response = http_get(
        config.HN_SEARCH_URL,
        params={"tags": "front_page", "hitsPerPage": config.HN_HITS},
        accept="application/json",
    )
    hits = response.json().get("hits", [])
    items: list[Item] = []
    for hit in hits:
        title = (hit.get("title") or "").strip()
        if not title:
            continue
        object_id = hit.get("objectID")
        hn_url = f"https://news.ycombinator.com/item?id={object_id}"
        # Prefer the article URL for display/dedup; fall back to the HN thread.
        url = hit.get("url") or hn_url
        points = int(hit.get("points") or 0)
        comments = int(hit.get("num_comments") or 0)

        tags = [f"💬 {fmt_int(comments)} 评论"] if comments else []
        if hit.get("url"):
            tags.append(f"🔗 讨论 {hn_url}")

        items.append(
            Item(
                id=url,
                title=title,
                url=url,
                source=key,
                category=category,
                summary_src=title,   # HN has no blurb; the summarizer works off the title + URL
                score=float(points),
                metric_label=f"🔺 {fmt_int(points)} 分",
                tags=[t for t in tags if not t.startswith("🔗")],
                source_label="Hacker News",
                published=hit.get("created_at"),
                translate_title=True,
                extra={"hn_url": hn_url, "comments": comments},
            )
        )
    logger.info("hackernews: parsed %d posts", len(items))
    return items
