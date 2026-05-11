"""Generate a short Chinese sales-pitch summary for each repo.

Provider-agnostic. Default uses GitHub Models (free, OpenAI-compatible
endpoint, auth via GITHUB_TOKEN). Switch via `config.SUMMARIZER_PROVIDER`.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Protocol

import httpx

from . import config
from .models import RepoMeta

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是技术资讯编辑。给定一个 GitHub 仓库的元数据,写一句中文卖点描述。

严格要求:
1. 【语言】输出必须是简体中文。即使输入描述是英文,也必须翻译并改写成中文,绝不允许直接返回英文。
2. 【字数】30~60 个汉字。
3. 【内容】突出具体技术点(框架名/方法/对比数字),基于描述里已有的事实,不要编造。
4. 【禁用词】不许出现这些虚词: 助力、赋能、高效、解决方案、强劲、动态、显著、深度赋能、生态、构建、提升、优化体验。
5. 【禁止】不要重复仓库名;不要用「这是一个」「该项目」开头;不要评价 star 增长(如"日增千星"等 meta 评价)。
6. 【格式】一句话,不分行,不要 markdown 符号,不要序号。

示例:
输入描述: "A modern, fast, all-in-one Python web framework"
输出: 单文件部署的 Python Web 框架,内置 ORM 与模板引擎,主打零依赖和异步原生。

输入描述: "Build powerful AI agents with multi-step reasoning"
输出: 用多步推理串联工具调用的智能体框架,代码 200 行起步,默认接 OpenAI 与本地模型。"""


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
            "temperature": 0.2,
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
    """Return {full_name: summary}. Individual failures fall back to description.

    Retries once on 429 with a 60s backoff (covers GitHub Models per-minute
    quotas for premium models like DeepSeek-V3).
    """
    results: dict[str, str] = {}
    for repo in repos:
        results[repo.full_name] = _summarize_with_retry(repo, summarizer)
    return results


def _summarize_with_retry(repo: RepoMeta, summarizer: Summarizer) -> str:
    for attempt in (1, 2):
        try:
            return summarizer.summarize(repo)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and attempt == 1:
                logger.warning("429 for %s, sleeping 60s then retrying once", repo.full_name)
                time.sleep(60)
                continue
            logger.warning("Summarize failed for %s: %s", repo.full_name, exc)
            break
        except Exception as exc:
            logger.warning("Summarize failed for %s: %s", repo.full_name, exc)
            break
    return repo.description or "(描述生成失败)"
