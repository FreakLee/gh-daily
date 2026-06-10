"""CLI entry point for gh-daily.

Usage:
    python -m src.main                    # daily, full pipeline, writes data + docs
    python -m src.main --mode weekly      # weekly (aggregation lands in next iter)
    python -m src.main --no-ai            # skip AI summarizer
    python -m src.main --dry-run          # do not write to data/ or docs/
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from . import config, fetch, history, render, select, snapshot, summarize

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = PROJECT_ROOT / "docs"
DB_PATH = DATA_DIR / "snapshots.db"
HISTORY_PATH = DATA_DIR / "history.json"
ARCHIVE_DIR = DOCS_DIR / "archive"


def main() -> int:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    parser = argparse.ArgumentParser(description="GitHub trending digest generator")
    parser.add_argument("--mode", choices=["daily", "weekly"], default="daily")
    parser.add_argument("--no-ai", action="store_true",
                        help="Skip AI; use raw description (for plumbing tests).")
    parser.add_argument("--provider", choices=["github_models", "claude", "none"], default=None)
    parser.add_argument("--max-picks", type=int, default=config.MAX_PICKS)
    parser.add_argument("--dry-run", action="store_true",
                        help="Do not write to data/ or docs/; just print markdown.")
    args = parser.parse_args()

    now = datetime.now(config.TIMEZONE)
    today = now.date()

    if args.mode == "weekly":
        print("[warn] weekly aggregation not wired yet; using daily flow.", file=sys.stderr)

    # 1. Fetch
    print("[1/6] Fetching github.com/trending ...", file=sys.stderr)
    try:
        candidates = fetch.fetch_trending()
    except Exception as exc:
        print(f"[fail] fetch_trending: {exc}", file=sys.stderr)
        return 2
    print(f"       got {len(candidates)} candidates", file=sys.stderr)

    # 2. Snapshot + delta
    print("[2/6] Snapshotting + computing deltas ...", file=sys.stderr)
    if not args.dry_run:
        snapshot.init_db(DB_PATH)
        snapshot.upsert_many(DB_PATH, today, candidates)

        # Replace trending's reported stars_today with computed delta where we
        # have historical data (otherwise keep trending's value as fallback).
        for repo in candidates:
            repo.stars_today = snapshot.compute_delta(DB_PATH, repo, today)

    # 3. Select (with 7-day dedup from history)
    print("[3/6] Selecting picks ...", file=sys.stderr)
    issues = history.load(HISTORY_PATH) if not args.dry_run else []
    dedup = history.recent_repos(issues, today, days=config.DEDUP_WINDOW_DAYS)
    picks = select.select_picks(candidates, max_picks=args.max_picks, dedup_against=dedup)

    if not select.is_enough(picks):
        print(
            f"[skip] only {len(picks)} repos passed delta>={config.MIN_DELTA_THRESHOLD}; "
            f"min is {config.MIN_PICKS}",
            file=sys.stderr,
        )
        return 0
    print(f"       picked {len(picks)} repos (excluded {len(dedup)} via history)",
          file=sys.stderr)

    # 4. Summarize
    provider = "none" if args.no_ai else args.provider
    print(f"[4/6] Summarizing (provider={provider or config.SUMMARIZER_PROVIDER}) ...",
          file=sys.stderr)
    try:
        summarizer = summarize.get_summarizer(provider)
    except RuntimeError as exc:
        print(f"[fail] summarizer init: {exc}", file=sys.stderr)
        return 2
    summaries = summarize.summarize_all(picks, summarizer)

    # 5. Render
    print("[5/6] Rendering markdown + HTML ...", file=sys.stderr)
    md_text = render.render_markdown(picks, summaries, mode=args.mode, now=now)
    html_text = render.render_full_page(picks, summaries, mode=args.mode, now=now)

    # 6. Write artifacts
    if args.dry_run:
        print("[6/6] dry-run: skipping disk writes", file=sys.stderr)
    else:
        print("[6/6] Writing artifacts ...", file=sys.stderr)
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

        today_html = DOCS_DIR / "today.html"
        archive_html = ARCHIVE_DIR / f"{today.isoformat()}.html"
        today_html.write_text(html_text, encoding="utf-8")
        archive_html.write_text(html_text, encoding="utf-8")

        history.append_issue(
            HISTORY_PATH,
            today=today,
            mode=args.mode,
            repos=[r.full_name for r in picks],
            url=f"{config.PAGES_BASE_URL}/archive/{today.isoformat()}.html"
                if hasattr(config, "PAGES_BASE_URL") else "",
        )

        # Re-read issues (now includes the one we just appended) and rebuild index
        issues = history.load(HISTORY_PATH)
        _write_index(DOCS_DIR / "index.html", issues)

        print(f"       wrote {today_html.relative_to(PROJECT_ROOT)}", file=sys.stderr)
        print(f"       wrote {archive_html.relative_to(PROJECT_ROOT)}", file=sys.stderr)

    print("", file=sys.stderr)
    print(md_text)
    return 0


def _write_index(index_path: Path, issues: list) -> None:
    """Plain reverse-chronological list of historical issues."""
    rows = []
    for issue in sorted(issues, key=lambda x: x["date"], reverse=True):
        date = issue["date"]
        mode = "周报" if issue["mode"] == "weekly" else "日报"
        n = len(issue["repos"])
        href = f"archive/{date}.html"
        rows.append(
            f'<li style="margin:6px 0;">'
            f'<a href="{href}" style="color:#3182ce;">{date} · {mode} · {n} 个仓库</a>'
            f"</li>"
        )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GitHub 日报 · 历史</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", "PingFang SC", sans-serif;
         max-width: 640px; margin: 0 auto; padding: 24px 16px; color: #2c3e50; }}
  h1 {{ font-size: 22px; }}
  ul {{ list-style: none; padding: 0; }}
  a {{ text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .latest {{ background: #f7fafc; padding: 12px; margin-bottom: 16px; border-left: 3px solid #07c160; }}
</style>
</head>
<body>
  <h1>GitHub 日报 · 历史</h1>
  <p class="latest">📌 <a href="today.html"><strong>查看最新一期</strong></a></p>
  <ul>{"".join(rows)}</ul>
</body>
</html>
"""
    index_path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
