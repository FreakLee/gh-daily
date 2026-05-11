"""Render the picked repos as a Markdown digest.

M1: Markdown only. HTML rendering lands in M2.
"""

from __future__ import annotations

from datetime import datetime

from . import config
from .models import RepoMeta

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def render_markdown(
    picks: list[RepoMeta],
    summaries: dict[str, str],
    *,
    mode: str = "daily",
    now: datetime | None = None,
) -> str:
    now = now or datetime.now(config.TIMEZONE)
    weekday = WEEKDAY_CN[now.weekday()]
    total_delta = sum(repo.stars_today for repo in picks)

    if mode == "weekly":
        title = f"GitHub 周报 · 第 {now.isocalendar().week} 周"
    else:
        title = f"GitHub 日报 · {now.month}月{now.day}日（{weekday}）"

    lines = [
        f"# {title}",
        "",
        f"今日 {len(picks)} 个仓库,共新增 ⭐ {_fmt_int(total_delta)}",
        "",
        "---",
        "",
    ]

    for i, repo in enumerate(picks, start=1):
        summary = summaries.get(repo.full_name) or repo.description or ""
        topic = repo.topics[0] if repo.topics else None
        meta_bits = [f"📈 +{_fmt_int(repo.stars_today)} ⭐"]
        if repo.language:
            meta_bits.append(f"🔧 {repo.language}")
        if topic:
            meta_bits.append(f"🏷️ {topic}")
        meta = "    ".join(meta_bits)

        lines.extend([
            f"**{i}. {repo.full_name}**",
            "",
            summary,
            "",
            meta,
            "",
            f"🔗 {repo.url}",
            "",
            "---",
            "",
        ])

    lines.extend([
        f"📅 本期生成时间: {now.strftime('%Y-%m-%d %H:%M')}",
        "",
        "💡 数据来源: GitHub Trending",
    ])
    return "\n".join(lines)


def _fmt_int(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k".rstrip("0").rstrip(".")
    return str(n)
