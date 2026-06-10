"""Publish history (data/history.json) — drives 7-day dedup and weekly tags."""

from __future__ import annotations

import json
from datetime import date as Date, timedelta
from pathlib import Path
from typing import TypedDict


class Issue(TypedDict):
    date: str        # 'YYYY-MM-DD'
    mode: str        # 'daily' | 'weekly'
    repos: list[str] # full_names
    url: str         # archive URL (empty in early milestones)


def load(history_path: Path) -> list[Issue]:
    if not history_path.exists():
        return []
    text = history_path.read_text(encoding="utf-8")
    if not text.strip():
        return []
    data = json.loads(text)
    return list(data.get("issues", []))


def save(history_path: Path, issues: list[Issue]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps({"issues": issues}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_issue(
    history_path: Path,
    today: Date,
    mode: str,
    repos: list[str],
    url: str = "",
) -> None:
    issues = load(history_path)
    issues.append(Issue(date=today.isoformat(), mode=mode, repos=repos, url=url))
    save(history_path, issues)


def recent_repos(issues: list[Issue], today: Date, days: int) -> set[str]:
    """Repos published in the last `days` days (excluding today)."""
    cutoff = today - timedelta(days=days)
    out: set[str] = set()
    for issue in issues:
        issue_date = Date.fromisoformat(issue["date"])
        if cutoff <= issue_date < today:
            out.update(issue["repos"])
    return out
