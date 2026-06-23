"""Generic RSS/Atom source, used for the finance line.

One instance per feed in `config.RSS_FEEDS`. Items are scored by recency, with
a large boost when the title/summary mentions a market-moving figure
(`config.FIGURE_KEYWORDS`) — this is the "靠新闻反向捞言论" approach: instead of
scraping X / Truth Social directly, we surface statements that financial outlets
already deemed important, and tag who they're about.
"""

from __future__ import annotations

import logging
import re
import time
from calendar import timegm

import feedparser

from .. import config
from ..models import Item
from .base import http_get

logger = logging.getLogger(__name__)


class RssSource:
    def __init__(self, key: str):
        self.key = key
        self.label, self.url, self.category, self.translate_title = config.RSS_FEEDS[key]

    def fetch(self) -> list[Item]:
        try:
            response = http_get(self.url, accept="application/rss+xml")
        except Exception as exc:
            logger.warning("rss %s: fetch failed: %s", self.key, exc)
            return []
        feed = feedparser.parse(response.text)
        now = time.time()
        items: list[Item] = []
        for entry in feed.entries[: config.RSS_PER_FEED]:
            item = self._parse(entry, now)
            if item is not None:
                items.append(item)
        logger.info("%s: kept %d items", self.key, len(items))
        return items

    def _parse(self, entry, now: float) -> Item | None:
        title = _clean(entry.get("title") or "")
        url = entry.get("link") or entry.get("id")
        if not title or not url:
            return None

        struct = entry.get("published_parsed") or entry.get("updated_parsed")
        age_hours = (now - timegm(struct)) / 3600 if struct else 0.0
        if age_hours > config.RSS_MAX_AGE_HOURS:
            return None

        summary = _clean(_strip_html(entry.get("summary") or ""))
        # Figure-boost is a finance device (statements move markets); skip it for
        # tech feeds so a stray Musk mention doesn't hijack the tech ranking.
        figures = _match_figures(f"{title} {summary}") if self.category == "finance" else []

        score = max(0.0, config.RSS_MAX_AGE_HOURS - age_hours)
        if figures:
            score += config.FIGURE_BOOST

        tags = [f"🗣️ {name}" for name in figures]

        return Item(
            id=url,
            title=title,
            url=url,
            source=self.key,
            category=self.category,
            summary_src=summary or title,
            score=score,
            metric_label="",   # RSS has no numeric heat; the source chip carries attribution
            tags=tags,
            source_label=self.label,
            published=entry.get("published") or entry.get("updated"),
            translate_title=self.translate_title,
            extra={"figures": figures},
        )


def make_source(key: str) -> RssSource:
    return RssSource(key)


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _TAG_RE.sub(" ", s)


def _clean(s: str) -> str:
    return " ".join(s.split()).strip()


def _match_figures(text: str) -> list[str]:
    lower = text.lower()
    hits = []
    for name, keywords in config.FIGURE_KEYWORDS.items():
        if any(kw.lower() in lower for kw in keywords):
            hits.append(name)
    return hits
