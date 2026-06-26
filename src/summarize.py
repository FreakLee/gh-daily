"""Generate a short Chinese summary for each item, tailored per category.

Provider-agnostic. Default uses GitHub Models (free, OpenAI-compatible endpoint,
auth via GITHUB_TOKEN). Switch via `config.SUMMARIZER_PROVIDER`.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Protocol

import httpx

from . import config
from .models import Item

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_TECH = """你是一个混迹 GitHub 和 Hacker News 很多年的资深工程师,在跟同行安利(或吐槽)一个东西。用一句大白话说清楚:它到底是干嘛的、巧在哪、谁会用得上。

要求:
1. 【语言】简体中文。英文输入要翻译改写成自然的中文口语,绝不直接返回英文,也不要翻译腔。
2. 【字数】25~55 个汉字,宁短勿凑。
3. 【说人话】像跟懂行的朋友聊天,不是写产品文案。可以有判断和态度(例如"终于有人做了""思路有点野""比 X 省事不少"),但判断要基于事实。
4. 【具体】点到关键技术点:框架/方法/对比数字/适用场景,基于已有信息,不编造。
5. 【禁用这些词】(一股 AI/营销味):助力、赋能、高效、解决方案、强大、轻松、完美、一站式、生态、构建、提升、优化体验、值得关注、不容错过、旨在、致力于、打造、聚焦、神器、宝藏、革命性、颠覆、前沿。
6. 【别这样开头】不要用"这是一个""该项目""本项目";不要复述标题原文;不要评价热度(如"日增千星")。
7. 【格式】一句话,可含逗号但不分行,不要 markdown、不要序号、不要引号包裹整句。
8. 【标点】中文标点一律用全角(，。、：；？！);英文单词、代码、版本号、数字内部的符号保持原样(如 GPT-5.2、Node.js)。

示例:
输入: "A modern, fast, all-in-one Python web framework"
输出: 路由、ORM、模板全塞进一个文件,零依赖原生异步,适合懒得配环境、想直接开干的小项目。

输入: "Build powerful AI agents with multi-step reasoning"
输出: 两百行代码就能跑起一个会自己拆任务、调工具的 agent,默认接 OpenAI,也能换本地模型,挺适合上手摸底。

输入: "A terminal-based file manager written in Rust"
输出: 用 Rust 写的终端文件管理器,主打快和键盘流,vim 党会很顺手。"""


SYSTEM_PROMPT_FINANCE = """你是一个看了十年盘、自己也真金白银在投的人,在跟读者唠一条财经消息。用一句话说清楚:发生了啥、钱可能往哪走、对哪类资产有影响。涉及大人物发言时,说清他说了什么、市场为什么会买账。

要求:
1. 【语言】简体中文。英文输入要翻译改写成自然中文,不要翻译腔。
2. 【字数】30~65 个汉字,宁短勿凑。
3. 【说人话】像懂行的人私下聊,有视角、有判断,但不喊单、不预测点位、不给买卖建议。落到具体:影响的是美债、科技股、黄金、美元还是别的。
4. 【人物发言】(特朗普、马斯克、黄仁勋、沃什等)先说他到底说了什么,再说市场为啥在意,别空泛。
   【事实校正,务必遵守】现任美联储主席是 Kevin Warsh(沃什),2026 年 5 月就任;鲍威尔已卸任主席(仍任理事)。凡涉及美联储/货币政策,主席一律按沃什处理,绝不要再说鲍威尔是现任主席。
5. 【禁用这些词】(套话/AI 味):利好、利空(直接说方向)、布局、风口、抄底、剑指、引爆、震荡(给具体)、暴涨暴跌(给幅度)、避险情绪升温、市场普遍认为、助力、赋能、值得关注。
6. 【别这样开头】不要用"这是""该消息""据悉";不要复述标题原文。不编造数据。
7. 【格式】一句话,可含逗号但不分行,不要 markdown、不要序号、不要引号包裹整句。
8. 【标点】中文标点一律用全角(，。、：；？！);英文单词、代码、版本号、数字内部的符号保持原样(如 GPT-5.2、Node.js)。

示例:
输入: 鲍威尔讲话暗示年内或再降息一次
输出: 鲍威尔松口说今年可能还有一次降息,美债收益率应声往下走,最吃这套预期的是科技股和黄金。

输入: 特朗普称考虑对进口芯片加征关税
输出: 特朗普放话要对进口芯片加税,真落地的话英伟达们的成本和供应链都得重算,半导体股先跌为敬。

输入: 某公司财报营收超预期但指引疲软
输出: 营收是漂亮,但下季度指引给得保守,盘后照样被砸,说明市场现在只认未来不认过去。"""


def _system_prompt(category: str) -> str:
    return SYSTEM_PROMPT_FINANCE if category == "finance" else SYSTEM_PROMPT_TECH


def _user_prompt(item: Item) -> str:
    lines = [
        f"标题: {item.title}",
        f"来源: {item.source_label or item.source}",
    ]
    if item.summary_src and item.summary_src != item.title:
        lines.append(f"原始描述: {item.summary_src}")
    if item.tags:
        lines.append(f"标签: {', '.join(item.tags)}")
    if item.extra.get("language"):
        lines.append(f"主语言: {item.extra['language']}")
    if item.extra.get("figures"):
        lines.append(f"涉及人物: {', '.join(item.extra['figures'])}")
    if item.translate_title:
        lines.append(
            "\n【额外·标题翻译】本条标题是外文。请严格按下面两行输出,不要任何多余内容:\n"
            "标题：<12字以内、地道、不啰嗦的中文标题,不加书名号引号>\n"
            "要点：<按上面要求的一句话中文要点>"
        )
    else:
        lines.append("\n请直接输出一句话中文要点,不要加任何前缀标签。")
    return "\n".join(lines)


class Summarizer(Protocol):
    def summarize(self, item: Item) -> str: ...
    def chat(self, system: str, user: str, *, temperature: float = 0.2) -> str: ...


class NoOpSummarizer:
    """Returns the source blurb verbatim. For plumbing tests."""

    def summarize(self, item: Item) -> str:
        return item.summary_src or item.title

    def chat(self, system: str, user: str, *, temperature: float = 0.2) -> str:
        return ""


class OpenAICompatSummarizer:
    """Any OpenAI-compatible chat-completions endpoint (GitHub Models, DeepSeek, ...).

    Auth is a Bearer token; the difference between providers is just endpoint +
    model + which env var holds the key.
    """

    def __init__(self, endpoint: str, model: str, api_key: str | None):
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        if not self.api_key:
            raise RuntimeError("API key missing for summarizer endpoint")

    def chat(self, system: str, user: str, *, temperature: float = 0.2) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": 300,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=config.SUMMARIZER_TIMEOUT_SECONDS) as client:
            response = client.post(self.endpoint, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    def summarize(self, item: Item) -> str:
        return self.chat(_system_prompt(item.category), _user_prompt(item))


def _github_models_summarizer() -> OpenAICompatSummarizer:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN not set. Create a PAT with `models:read` scope at "
            "https://github.com/settings/tokens and put it in .env"
        )
    return OpenAICompatSummarizer(config.GH_MODELS_ENDPOINT, config.SUMMARIZER_GH_MODEL, token)


def _deepseek_summarizer() -> OpenAICompatSummarizer:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY not set. Create one at https://platform.deepseek.com "
            "(API keys), top up a small balance, and put it in .env"
        )
    return OpenAICompatSummarizer(
        config.DEEPSEEK_ENDPOINT, config.SUMMARIZER_DEEPSEEK_MODEL, key
    )


class ClaudeSummarizer:
    """Anthropic Messages API. Optional fallback / quality comparison."""

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

    def chat(self, system: str, user: str, *, temperature: float = 0.2) -> str:
        body = {
            "model": self.model,
            "max_tokens": 300,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
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

    def summarize(self, item: Item) -> str:
        return self.chat(_system_prompt(item.category), _user_prompt(item))


def get_summarizer(provider: str | None = None) -> Summarizer:
    provider = provider or config.SUMMARIZER_PROVIDER
    if provider == "deepseek":
        return _deepseek_summarizer()
    if provider == "github_models":
        return _github_models_summarizer()
    if provider == "claude":
        return ClaudeSummarizer()
    if provider == "none":
        return NoOpSummarizer()
    raise ValueError(f"Unknown summarizer provider: {provider!r}")


def summarize_all(items: list[Item], summarizer: Summarizer) -> None:
    """Fill `item.ai_summary` (and `item.title_zh` when translating) in place.
    Individual failures fall back to the blurb / original title."""
    for item in items:
        raw = _summarize_with_retry(item, summarizer)
        if item.translate_title:
            title_zh, summary = _parse_titled(raw)
            if title_zh:
                item.title_zh = _normalize_punct(title_zh)
            item.ai_summary = _normalize_punct(summary)
        else:
            item.ai_summary = _normalize_punct(raw)


# Half-width -> full-width, applied only when the punctuation touches a Chinese
# character, so English/code/version/number tokens (GPT-5.2, 1,000, Node.js,
# Markdown 或 JSON) keep their original ASCII punctuation.
_CJK = r"[一-鿿]"
_PUNCT_MAP = {
    ",": "，", ".": "。", ":": "：", ";": "；", "?": "？", "!": "！",
    "(": "（", ")": "）",
}


def _normalize_punct(text: str) -> str:
    if not text:
        return text
    for ascii_p, full_p in _PUNCT_MAP.items():
        p = re.escape(ascii_p)
        text = re.sub(rf"(?<={_CJK}){p}|{p}(?={_CJK})", full_p, text)
    return text


def _parse_titled(raw: str) -> tuple[str | None, str]:
    """Parse the two-line 标题/要点 format. Lenient: tolerates ：or : and stray text."""
    title = None
    summary = None
    for line in raw.splitlines():
        line = line.strip().lstrip("-*# ").strip()
        if line.startswith("标题"):
            title = line[2:].lstrip("：: ").strip() or None
        elif line.startswith("要点"):
            summary = line[2:].lstrip("：: ").strip() or None
    if summary is None:
        # model ignored the format — treat the whole thing as the summary
        summary = raw.strip()
    return title, summary


def _summarize_with_retry(item: Item, summarizer: Summarizer) -> str:
    for attempt in (1, 2):
        try:
            return summarizer.summarize(item)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and attempt == 1:
                logger.warning("429 for %s, sleeping 60s then retrying once", item.title[:40])
                time.sleep(60)
                continue
            logger.warning("Summarize failed for %s: %s", item.title[:40], exc)
            break
        except Exception as exc:
            logger.warning("Summarize failed for %s: %s", item.title[:40], exc)
            break
    return item.summary_src or "(描述生成失败)"
