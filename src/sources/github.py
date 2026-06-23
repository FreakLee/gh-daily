"""GitHub Trending source.

Scrapes github.com/trending. The CSS selectors are the only thing that needs
changing if GitHub updates the Trending DOM — keep them version-able here.

`Item.score` is the trending-reported daily star delta; main.py may overwrite it
with a snapshot-computed delta when historical data exists (see snapshot.py).
`extra` carries the fields the snapshot store and delta math need.
"""

from __future__ import annotations

import logging
import re
from typing import Final

from bs4 import BeautifulSoup, Tag

from .. import config
from ..models import Item
from .base import fmt_int, http_get

logger = logging.getLogger(__name__)

key = "github"
category = "tech"

SEL_ROW: Final = "article.Box-row"
SEL_REPO_LINK: Final = "h2 a"
SEL_DESCRIPTION: Final = "p.col-9"
SEL_LANGUAGE: Final = '[itemprop="programmingLanguage"]'
SEL_STARS_TOTAL: Final = 'a.Link--muted[href$="/stargazers"]'
SEL_STARS_TODAY: Final = "span.d-inline-block.float-sm-right"

_NUM_RE = re.compile(r"([\d,]+)")


def fetch() -> list[Item]:
    response = http_get(config.TRENDING_URL, accept="text/html")
    soup = BeautifulSoup(response.text, "html.parser")
    items: list[Item] = []
    for row in soup.select(SEL_ROW):
        item = _parse_row(row)
        if item is not None:
            items.append(item)
    logger.info("github: parsed %d repos", len(items))
    return items


def _parse_row(row: Tag) -> Item | None:
    link = row.select_one(SEL_REPO_LINK)
    if link is None or not link.get("href"):
        return None

    href = link["href"].strip()
    full_name = href.lstrip("/")
    if "/" not in full_name:
        return None

    url = f"https://github.com{href}"
    desc_tag = row.select_one(SEL_DESCRIPTION)
    description = _clean(desc_tag.get_text()) if desc_tag else None
    lang_tag = row.select_one(SEL_LANGUAGE)
    language = _clean(lang_tag.get_text()) if lang_tag else None
    stars_total = _extract_int(row.select_one(SEL_STARS_TOTAL))
    stars_today = _extract_int(row.select_one(SEL_STARS_TODAY))

    tags = []
    if language:
        tags.append(f"🔧 {language}")

    return Item(
        id=url,
        title=full_name,
        url=url,
        source=key,
        category=category,
        summary_src=description,
        score=float(stars_today),
        metric_label=f"📈 +{fmt_int(stars_today)} ⭐",
        tags=tags,
        source_label="GitHub",
        extra={
            "stars_total": stars_total,
            "stars_today": stars_today,
            "language": language,
        },
    )


def _extract_int(tag: Tag | None) -> int:
    if tag is None:
        return 0
    match = _NUM_RE.search(tag.get_text())
    return int(match.group(1).replace(",", "")) if match else 0


def _clean(s: str) -> str:
    return " ".join(s.split()).strip()
