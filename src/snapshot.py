"""SQLite-backed daily snapshot store.

Schema follows docs/superpowers/specs/2026-05-11-github-daily-design.md §3.1.
Idempotent on re-runs: primary key (snapshot_date, repo_full_name).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import date as Date
from pathlib import Path

from .models import RepoMeta

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_date  TEXT NOT NULL,
    repo_full_name TEXT NOT NULL,
    stars          INTEGER NOT NULL,
    description    TEXT,
    language       TEXT,
    topics         TEXT,
    source         TEXT NOT NULL,
    PRIMARY KEY (snapshot_date, repo_full_name)
);
CREATE INDEX IF NOT EXISTS idx_repo_date
    ON snapshots(repo_full_name, snapshot_date);
"""


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


def upsert_snapshot(db_path: Path, snapshot_date: Date, repo: RepoMeta) -> None:
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO snapshots"
            " (snapshot_date, repo_full_name, stars, description, language, topics, source)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot_date.isoformat(),
                repo.full_name,
                repo.stars_total,
                repo.description,
                repo.language,
                json.dumps(repo.topics, ensure_ascii=False),
                repo.source,
            ),
        )
        conn.commit()


def upsert_many(db_path: Path, snapshot_date: Date, repos: list[RepoMeta]) -> None:
    if not repos:
        return
    with closing(sqlite3.connect(db_path)) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO snapshots"
            " (snapshot_date, repo_full_name, stars, description, language, topics, source)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    snapshot_date.isoformat(),
                    r.full_name,
                    r.stars_total,
                    r.description,
                    r.language,
                    json.dumps(r.topics, ensure_ascii=False),
                    r.source,
                )
                for r in repos
            ],
        )
        conn.commit()


def get_previous_stars(
    db_path: Path,
    repo_full_name: str,
    before_date: Date,
) -> int | None:
    """Most recent star count strictly before `before_date`. None if not seen."""
    with closing(sqlite3.connect(db_path)) as conn:
        row = conn.execute(
            "SELECT stars FROM snapshots"
            " WHERE repo_full_name = ? AND snapshot_date < ?"
            " ORDER BY snapshot_date DESC LIMIT 1",
            (repo_full_name, before_date.isoformat()),
        ).fetchone()
    return row[0] if row else None


def snapshots_in_range(
    db_path: Path,
    start_date: Date,
    end_date: Date,
) -> list[tuple[str, str, int]]:
    """For weekly aggregation: returns [(date, repo, stars), ...]."""
    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT snapshot_date, repo_full_name, stars FROM snapshots"
            " WHERE snapshot_date >= ? AND snapshot_date <= ?"
            " ORDER BY repo_full_name, snapshot_date",
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()
    return rows


def compute_delta(
    db_path: Path,
    repo: RepoMeta,
    today: Date,
) -> int:
    """Today's star delta, computed from the most recent earlier snapshot.

    Falls back to `repo.stars_today` (which trending reports directly) when
    we've never seen this repo before — common in early days before the
    snapshot history fills in.
    """
    prev = get_previous_stars(db_path, repo.full_name, today)
    if prev is None:
        return repo.stars_today
    return max(0, repo.stars_total - prev)
