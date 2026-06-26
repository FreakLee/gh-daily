"""WeChat 公众号 draft creation — LOCAL ONLY.

Why local: WeChat requires the caller's public IP to be in the account's IP
whitelist to obtain an access_token. GitHub Actions IPs are dynamic, so the draft
step runs from your Mac (home IP whitelisted), the same place Draw Things runs.

Flow per issue: get access_token (cached) → upload the cover as a permanent image
material (→ thumb_media_id) → draft/add with the inlined HTML body. You then open
the 公众号 App and tap publish.

Credentials come from .env: WECHAT_APPID, WECHAT_APPSECRET.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import httpx

from . import config

logger = logging.getLogger(__name__)

_TOKEN_CACHE = Path(__file__).resolve().parent.parent / ".wechat_token.json"


class WeChatError(RuntimeError):
    pass


def _check(data: dict) -> dict:
    # WeChat returns errcode 0 (or omits it) on success.
    if data.get("errcode"):
        raise WeChatError(f"errcode={data['errcode']} errmsg={data.get('errmsg')}")
    return data


def get_access_token(appid: str, secret: str) -> str:
    """Fetch (and cache to disk for ~2h) an access_token."""
    now = time.time()
    if _TOKEN_CACHE.exists():
        try:
            cached = json.loads(_TOKEN_CACHE.read_text())
            if cached.get("appid") == appid and cached.get("expires_at", 0) > now + 120:
                return cached["access_token"]
        except Exception:
            pass

    resp = httpx.get(
        config.WECHAT_TOKEN_ENDPOINT,
        params={"grant_type": "client_credential", "appid": appid, "secret": secret},
        timeout=config.WECHAT_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = _check(resp.json())
    token = data["access_token"]
    _TOKEN_CACHE.write_text(json.dumps({
        "appid": appid,
        "access_token": token,
        "expires_at": now + int(data.get("expires_in", 7200)),
    }))
    return token


def upload_image_material(token: str, png_bytes: bytes, name: str = "cover.png") -> str:
    """Upload a permanent image material; return its media_id (usable as thumb)."""
    resp = httpx.post(
        config.WECHAT_MATERIAL_ENDPOINT,
        params={"access_token": token, "type": "image"},
        files={"media": (name, png_bytes, "image/png")},
        timeout=config.WECHAT_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return _check(resp.json())["media_id"]


def add_draft(token: str, *, title: str, author: str, digest: str,
              content_html: str, thumb_media_id: str) -> str:
    """Create a single-article draft; return the draft media_id."""
    article = {
        "title": title[:64],            # WeChat title limit
        "author": author,
        "digest": digest[:120],
        "content": content_html,
        "thumb_media_id": thumb_media_id,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }
    body = json.dumps({"articles": [article]}, ensure_ascii=False).encode("utf-8")
    resp = httpx.post(
        config.WECHAT_DRAFT_ENDPOINT,
        params={"access_token": token},
        content=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=config.WECHAT_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return _check(resp.json())["media_id"]


def create_draft(*, title: str, content_html: str, digest: str,
                 cover_png: bytes | None) -> str | None:
    """Best-effort: build one WeChat draft. Returns draft media_id or None.

    Requires WECHAT_APPID/WECHAT_APPSECRET in env and a cover image (WeChat
    drafts require a 封面/thumb). Any failure logs a warning and returns None so
    the rest of the run is unaffected.
    """
    appid = os.environ.get("WECHAT_APPID")
    secret = os.environ.get("WECHAT_APPSECRET")
    if not (appid and secret):
        logger.warning("WECHAT_APPID/WECHAT_APPSECRET not set; skipping WeChat draft")
        return None
    if not cover_png:
        logger.warning("no cover image (Draw Things off?); WeChat draft needs a 封面, skipping")
        return None
    try:
        token = get_access_token(appid, secret)
        thumb_media_id = upload_image_material(token, cover_png)
        return add_draft(
            token,
            title=title,
            author=config.WECHAT_AUTHOR,
            digest=digest,
            content_html=content_html,
            thumb_media_id=thumb_media_id,
        )
    except WeChatError as exc:
        logger.warning("WeChat draft failed: %s "
                       "(常见原因:IP 未加白名单 / 接口权限不足 / AppSecret 错)", exc)
        return None
    except Exception as exc:
        logger.warning("WeChat draft failed: %s", exc)
        return None
