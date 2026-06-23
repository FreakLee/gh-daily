"""CLI entry point for gh-daily.

Runs one independent issue per category (科技/AI 日报, 财经晨报). Each issue:
fetch its sources → (GitHub) snapshot + delta → dedup → quota-select → summarize
→ render Markdown + HTML → write docs/<category>/.

Usage:
    python -m src.main                       # all categories, full pipeline
    python -m src.main --category finance    # just one category
    python -m src.main --no-ai               # skip AI summarizer
    python -m src.main --dry-run             # print markdown only; no disk writes
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from . import config, history, illustrate, render, select, snapshot, sources, summarize
from .models import Item

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = PROJECT_ROOT / "docs"
DB_PATH = DATA_DIR / "snapshots.db"

log = logging.getLogger("gh-daily")


def main() -> int:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    parser = argparse.ArgumentParser(description="Multi-source tech & finance digest generator")
    parser.add_argument("--category", choices=config.CATEGORIES, default=None,
                        help="Run only this category (default: all).")
    parser.add_argument("--no-ai", action="store_true",
                        help="Skip AI; use raw blurb (plumbing test).")
    parser.add_argument("--provider", choices=["deepseek", "github_models", "claude", "none"],
                        default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="Do not write to data/ or docs/; just print markdown.")
    parser.add_argument("--no-image", action="store_true",
                        help="Skip the Draw Things cover image.")
    args = parser.parse_args()

    now = datetime.now(config.TIMEZONE)
    categories = [args.category] if args.category else config.CATEGORIES

    provider = "none" if args.no_ai else args.provider
    try:
        summarizer = summarize.get_summarizer(provider)
    except RuntimeError as exc:
        print(f"[fail] summarizer init: {exc}", file=sys.stderr)
        return 2

    exit_code = 0
    for category in categories:
        rc = run_category(category, summarizer, now, dry_run=args.dry_run, no_image=args.no_image)
        exit_code = exit_code or rc

    if not args.dry_run:
        _write_root_index(DOCS_DIR / "index.html", now)

    return exit_code


def run_category(category: str, summarizer, now: datetime, *, dry_run: bool, no_image: bool) -> int:
    today = now.date()
    label = config.CATEGORY_TITLES.get(category, category)
    print(f"\n========== {label} ==========", file=sys.stderr)

    # 1. Fetch every source for this category.
    items: list[Item] = []
    for source in sources.get_sources(category):
        try:
            items.extend(source.fetch())
        except Exception as exc:
            print(f"[warn] source {source.key} failed: {exc}", file=sys.stderr)
    if not items:
        print(f"[skip] {category}: no items fetched", file=sys.stderr)
        return 0
    print(f"[1/6] fetched {len(items)} items", file=sys.stderr)

    # 2. Snapshot + delta (GitHub stars only).
    if not dry_run:
        snapshot.init_db(DB_PATH)
        gh_items = [it for it in items if it.source == "github"]
        snapshot.upsert_many(DB_PATH, today, gh_items)
        for it in gh_items:
            it.score = snapshot.compute_delta(DB_PATH, it, today)

    # 3. Dedup against this category's recent history.
    hist_path = DATA_DIR / f"history-{category}.json"
    issues = history.load(hist_path) if not dry_run else []
    dedup = history.recent_ids(issues, today, days=config.DEDUP_WINDOW_DAYS)

    # 4. Quota select.
    picks = select.select_for_category(items, sources.quotas(category), dedup_against=dedup)
    if not select.is_enough(picks):
        print(f"[skip] {category}: only {len(picks)} picks (min {config.MIN_PICKS})",
              file=sys.stderr)
        return 0
    print(f"[2/6] selected {len(picks)} picks (excluded {len(dedup)} via history)",
          file=sys.stderr)

    # 5. Summarize (fills item.ai_summary).
    print(f"[3/6] summarizing (provider={summarizer.__class__.__name__}) ...", file=sys.stderr)
    summarize.summarize_all(picks, summarizer)

    # 6. Cover image (local Draw Things; best-effort).
    cover_png: bytes | None = None
    cover_uri: str | None = None
    if not dry_run and not no_image and config.ENABLE_COVER_IMAGE:
        print("[4/6] generating cover via Draw Things ...", file=sys.stderr)
        cover_png = illustrate.make_cover(picks, category, summarizer)
        if cover_png:
            cover_uri = illustrate.to_data_uri(cover_png)
            print(f"       got cover ({len(cover_png) // 1024} KB)", file=sys.stderr)

    # 7. Render.
    print("[5/6] rendering markdown + HTML ...", file=sys.stderr)
    md_text = render.render_markdown(picks, category=category, now=now)
    html_text = render.render_full_page(picks, category=category, now=now, cover_data_uri=cover_uri)

    # 8. Write artifacts.
    if dry_run:
        print("[6/6] dry-run: skipping disk writes", file=sys.stderr)
    else:
        cat_dir = DOCS_DIR / category
        archive_dir = cat_dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        (cat_dir / "today.html").write_text(html_text, encoding="utf-8")
        (archive_dir / f"{today.isoformat()}.html").write_text(html_text, encoding="utf-8")
        if cover_png:
            # Saved separately too, so you can drag it in / set as the 公众号 封面.
            (cat_dir / "today.png").write_bytes(cover_png)
            (archive_dir / f"{today.isoformat()}.png").write_bytes(cover_png)

        history.append_issue(
            hist_path, today=today, category=category, mode="daily",
            items=[it.id for it in picks],
            url=f"{category}/archive/{today.isoformat()}.html",
        )
        _write_category_index(cat_dir / "index.html", category, history.load(hist_path))
        print(f"[6/6] wrote docs/{category}/today.html (+ archive)", file=sys.stderr)

    print(f"\n{md_text}")
    return 0


# -------- Index pages --------


def _write_category_index(index_path: Path, category: str, issues: list) -> None:
    label = config.CATEGORY_TITLES.get(category, category)
    rows = []
    for issue in sorted(issues, key=lambda x: x["date"], reverse=True):
        date = issue["date"]
        n = len(issue.get("items", []))
        rows.append(
            f'<li style="margin:6px 0;"><a href="archive/{date}.html" '
            f'style="color:#3182ce;">{date} · {n} 条</a></li>'
        )
    html = _INDEX_TEMPLATE.format(
        title=f"{label} · 历史",
        heading=f"{label} · 历史",
        latest_href="today.html",
        rows="".join(rows),
    )
    index_path.write_text(html, encoding="utf-8")


def _write_root_index(index_path: Path, now: datetime) -> None:
    cards = []
    for category in config.CATEGORIES:
        label = config.CATEGORY_TITLES.get(category, category)
        cards.append(
            f'<p class="latest">📌 <a href="{category}/today.html"><strong>{label} · 最新一期</strong></a>'
            f' &nbsp;·&nbsp; <a href="{category}/index.html" style="color:#3182ce;">历史</a></p>'
        )
    html = _INDEX_TEMPLATE.format(
        title="gh-daily · 科技与财经日报",
        heading="gh-daily",
        latest_href="",
        rows="",
    ).replace("<ul></ul>", "".join(cards))
    index_path.write_text(html, encoding="utf-8")


_INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", "PingFang SC", sans-serif;
         max-width: 640px; margin: 0 auto; padding: 24px 16px; color: #2c3e50; }}
  h1 {{ font-size: 22px; }}
  ul {{ list-style: none; padding: 0; }}
  a {{ text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .latest {{ background: #f7fafc; padding: 12px; margin-bottom: 12px; border-left: 3px solid #07c160; }}
</style>
</head>
<body>
  <h1>{heading}</h1>
  <ul>{rows}</ul>
</body>
</html>
"""


if __name__ == "__main__":
    sys.exit(main())
