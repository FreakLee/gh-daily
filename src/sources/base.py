"""Source protocol + shared HTTP helper.

Every source exposes a module-level `fetch() -> list[Item]`. A source ranks its
own items via `Item.score`; cross-source comparison is handled by quotas in
`select.py`, never here.
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from .. import config
from ..models import Item

logger = logging.getLogger(__name__)


class Source(Protocol):
    key: str          # matches the quota keys in config (e.g. "github")
    category: str     # "tech" | "finance"

    def fetch(self) -> list[Item]: ...


def http_get(url: str, *, params: dict | None = None, accept: str = "*/*") -> httpx.Response:
    headers = {"User-Agent": config.HTTP_USER_AGENT, "Accept": accept}
    with httpx.Client(
        timeout=config.HTTP_TIMEOUT_SECONDS, headers=headers, follow_redirects=True
    ) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        return response


def fmt_int(n: int | float) -> str:
    n = int(n)
    if n >= 1000:
        return f"{n / 1000:.1f}k".rstrip("0").rstrip(".")
    return str(n)
