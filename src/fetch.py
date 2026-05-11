"""Fetch trending repositories from github.com/trending.

The selectors below are the only place that needs to change if GitHub updates
the Trending page DOM. Keep them version-able here.
"""

from __future__ import annotations

import re
from typing import Final

import httpx
from bs4 import BeautifulSoup, Tag

from . import config
from .models import RepoMeta

# GitHub Trending DOM selectors (version-tied; update here only).
SEL_ROW: Final = "article.Box-row"
SEL_REPO_LINK: Final = "h2 a"
SEL_DESCRIPTION: Final = "p.col-9"
SEL_LANGUAGE: Final = '[itemprop="programmingLanguage"]'
SEL_STARS_TOTAL: Final = 'a.Link--muted[href$="/stargazers"]'
SEL_STARS_TODAY: Final = "span.d-inline-block.float-sm-right"


def fetch_trending() -> list[RepoMeta]:
    """Scrape github.com/trending. Returns repos in page order.

    Raises httpx.HTTPError on network failure. Returns empty list if page
    loads but contains no rows (e.g., GitHub broke the page).
    """
    headers = {
        "User-Agent": config.HTTP_USER_AGENT,
        "Accept": "text/html",
    }
    with httpx.Client(timeout=config.TRENDING_TIMEOUT_SECONDS, headers=headers) as client:
        response = client.get(config.TRENDING_URL)
        response.raise_for_status()
    return _parse(response.text)


def _parse(html: str) -> list[RepoMeta]:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select(SEL_ROW)
    repos: list[RepoMeta] = []
    for row in rows:
        repo = _parse_row(row)
        if repo is not None:
            repos.append(repo)
    return repos


def _parse_row(row: Tag) -> RepoMeta | None:
    link = row.select_one(SEL_REPO_LINK)
    if link is None or not link.get("href"):
        return None

    href = link["href"].strip()
    full_name = href.lstrip("/")
    if "/" not in full_name:
        return None

    url = f"https://github.com{href}"

    desc_tag = row.select_one(SEL_DESCRIPTION)
    description = _clean_text(desc_tag.get_text()) if desc_tag else None

    lang_tag = row.select_one(SEL_LANGUAGE)
    language = _clean_text(lang_tag.get_text()) if lang_tag else None

    stars_total = _extract_int(row.select_one(SEL_STARS_TOTAL))
    stars_today = _extract_int(row.select_one(SEL_STARS_TODAY))

    return RepoMeta(
        full_name=full_name,
        url=url,
        description=description,
        language=language,
        topics=[],          # trending page doesn't expose topics; M2 may enrich via API
        stars_total=stars_total,
        stars_today=stars_today,
        source="trending",
    )


_NUM_RE = re.compile(r"([\d,]+)")


def _extract_int(tag: Tag | None) -> int:
    if tag is None:
        return 0
    match = _NUM_RE.search(tag.get_text())
    if match is None:
        return 0
    return int(match.group(1).replace(",", ""))


def _clean_text(s: str) -> str:
    return " ".join(s.split()).strip()
