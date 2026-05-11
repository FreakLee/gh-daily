"""Generate a short Chinese sales-pitch summary for each repo.

Provider-agnostic. Default uses GitHub Models (free, OpenAI-compatible
endpoint, auth via GITHUB_TOKEN). Switch via `config.SUMMARIZER_PROVIDER`.
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

import httpx

from . import config
from .models import RepoMeta

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "你是技术资讯编辑。给定一个 GitHub 仓库的元数据,用 30~60 字中文写一句"
    "卖点描述,突出「解决什么问题 + 亮点」。不要重复仓库名,不要用「这是一个」"
    "这种废话开头。直接给一句话,不要分行,不要 markdown 格式。"
)


def _user_prompt(repo: RepoMeta) -> str:
    topics = ", ".join(repo.topics) if repo.topics else "(无)"
    return (
        f"仓库: {repo.full_name}\n"
        f"描述: {repo.description or '(无)'}\n"
        f"主语言: {repo.language or '(未知)'}\n"
        f"Topics: {topics}\n"
        f"当前 star 数: {repo.stars_total}\n"
        f"今日新增 star: {repo.stars_today}"
    )


class Summarizer(Protocol):
    def summarize(self, repo: RepoMeta) -> str: ...


class NoOpSummarizer:
    """Returns the English description verbatim. For plumbing tests."""

    def summarize(self, repo: RepoMeta) -> str:
        return repo.description or "(no description)"


class GitHubModelsSummarizer:
    """Calls GitHub Models (OpenAI-compatible) using a GitHub PAT.

    Requires the token to have `models:read` scope.
    """

    def __init__(self, model: str = config.SUMMARIZER_GH_MODEL, token: str | None = None):
        self.model = model
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise RuntimeError(
                "GITHUB_TOKEN not set. Create a PAT with `models:read` scope at "
                "https://github.com/settings/tokens and put it in .env"
            )

    def summarize(self, repo: RepoMeta) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(repo)},
            ],
            "temperature": 0.4,
            "max_tokens": 200,
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=config.SUMMARIZER_TIMEOUT_SECONDS) as client:
            response = client.post(config.GH_MODELS_ENDPOINT, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"].strip()


class ClaudeSummarizer:
    """Calls Anthropic Messages API. Optional fallback / quality comparison."""

    def __init__(
        self,
        model: str = config.SUMMARIZER_CLAUDE_MODEL,
        api_key: str | None = None,
    ):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Required when SUMMARIZER_PROVIDER=claude."
            )

    def summarize(self, repo: RepoMeta) -> str:
        body = {
            "model": self.model,
            "max_tokens": 200,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": _user_prompt(repo)}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        with httpx.Client(timeout=config.SUMMARIZER_TIMEOUT_SECONDS) as client:
            response = client.post(
                "https://api.anthropic.com/v1/messages", json=body, headers=headers
            )
            response.raise_for_status()
            data = response.json()
        return data["content"][0]["text"].strip()


def get_summarizer(provider: str | None = None) -> Summarizer:
    provider = provider or config.SUMMARIZER_PROVIDER
    if provider == "github_models":
        return GitHubModelsSummarizer()
    if provider == "claude":
        return ClaudeSummarizer()
    if provider == "none":
        return NoOpSummarizer()
    raise ValueError(f"Unknown summarizer provider: {provider!r}")


def summarize_all(
    repos: list[RepoMeta],
    summarizer: Summarizer,
) -> dict[str, str]:
    """Return {full_name: summary}. Individual failures fall back to description."""
    results: dict[str, str] = {}
    for repo in repos:
        try:
            results[repo.full_name] = summarizer.summarize(repo)
        except Exception as exc:
            logger.warning("Summarize failed for %s: %s", repo.full_name, exc)
            results[repo.full_name] = repo.description or "(描述生成失败)"
    return results
