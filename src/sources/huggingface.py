"""Hugging Face Daily Papers (curated AI papers, free JSON API, no key).

Highest signal-to-noise AI source: human-curated daily, with upvotes.
"""

from __future__ import annotations

import logging

from .. import config
from ..models import Item
from .base import fmt_int, http_get

logger = logging.getLogger(__name__)

key = "huggingface"
category = "tech"


def fetch() -> list[Item]:
    response = http_get(
        config.HF_DAILY_PAPERS_URL,
        params={"limit": config.HF_LIMIT},
        accept="application/json",
    )
    entries = response.json()
    items: list[Item] = []
    for entry in entries:
        paper = entry.get("paper", {})
        title = (entry.get("title") or paper.get("title") or "").strip()
        paper_id = paper.get("id")
        if not title or not paper_id:
            continue
        url = f"https://huggingface.co/papers/{paper_id}"
        upvotes = int(paper.get("upvotes") or 0)
        abstract = (paper.get("summary") or entry.get("summary") or "").strip()

        tags = []
        if paper.get("githubRepo"):
            tags.append("🧩 含代码")

        items.append(
            Item(
                id=url,
                title=title,
                url=url,
                source=key,
                category=category,
                summary_src=abstract,
                score=float(upvotes),
                metric_label=f"👍 {fmt_int(upvotes)}",
                tags=tags,
                source_label="HF Papers",
                published=entry.get("publishedAt"),
                extra={"arxiv_id": paper_id},
            )
        )
    logger.info("huggingface: parsed %d papers", len(items))
    return items
