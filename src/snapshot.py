"""SQLite-backed daily snapshot store, used for GitHub star deltas.

Only sources with a monotonic count (GitHub stars) snapshot here; HN/papers/RSS
score themselves at fetch time. Idempotent on re-runs via PK (date, item_id).
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date as Date
from pathlib import Path

from .models import Item

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_date  TEXT NOT NULL,
    item_id        TEXT NOT NULL,
    stars          INTEGER NOT NULL,
    title          TEXT,
    source         TEXT NOT NULL,
    PRIMARY KEY (snapshot_date, item_id)
);
CREATE INDEX IF NOT EXISTS idx_item_date
    ON snapshots(item_id, snapshot_date);
"""


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


def _stars(item: Item) -> int | None:
    val = item.extra.get("stars_total")
    return int(val) if val is not None else None


def upsert_many(db_path: Path, snapshot_date: Date, items: list[Item]) -> None:
    rows = [
        (snapshot_date.isoformat(), it.id, _stars(it), it.title, it.source)
        for it in items
        if _stars(it) is not None
    ]
    if not rows:
        return
    with closing(sqlite3.connect(db_path)) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO snapshots"
            " (snapshot_date, item_id, stars, title, source) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()


def get_previous_stars(db_path: Path, item_id: str, before_date: Date) -> int | None:
    """Most recent star count strictly before `before_date`. None if not seen."""
    with closing(sqlite3.connect(db_path)) as conn:
        row = conn.execute(
            "SELECT stars FROM snapshots"
            " WHERE item_id = ? AND snapshot_date < ?"
            " ORDER BY snapshot_date DESC LIMIT 1",
            (item_id, before_date.isoformat()),
        ).fetchone()
    return row[0] if row else None


def compute_delta(db_path: Path, item: Item, today: Date) -> float:
    """Today's star delta from the most recent earlier snapshot.

    Falls back to the source-reported score (trending's own daily delta) when the
    repo has no prior snapshot — common early on before history fills in.
    """
    stars_total = _stars(item)
    if stars_total is None:
        return item.score
    prev = get_previous_stars(db_path, item.id, today)
    if prev is None:
        return item.score
    return float(max(0, stars_total - prev))
