"""CLI entry point for gh-daily.

M1 usage:
    python -m src.main --mode daily
    python -m src.main --mode daily --no-ai     # skip AI, use raw description
"""

from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

from . import config, fetch, render, select, summarize


def main() -> int:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    parser = argparse.ArgumentParser(description="GitHub trending digest generator")
    parser.add_argument(
        "--mode",
        choices=["daily", "weekly"],
        default="daily",
        help="Issue type (weekly aggregation lands in M2+).",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip AI summarizer (uses raw description; for plumbing tests).",
    )
    parser.add_argument(
        "--provider",
        choices=["github_models", "claude", "none"],
        default=None,
        help="Override SUMMARIZER_PROVIDER from config.",
    )
    parser.add_argument(
        "--max-picks",
        type=int,
        default=config.MAX_PICKS,
        help=f"Max repos to include (default {config.MAX_PICKS}).",
    )
    args = parser.parse_args()

    if args.mode == "weekly":
        print("[warn] --mode weekly aggregation lands in M2+; falling back to daily flow.",
              file=sys.stderr)

    # 1. Fetch
    print("[1/4] Fetching github.com/trending ...", file=sys.stderr)
    try:
        candidates = fetch.fetch_trending()
    except Exception as exc:
        print(f"[fail] fetch_trending: {exc}", file=sys.stderr)
        return 2
    print(f"       got {len(candidates)} candidates", file=sys.stderr)

    # 2. Select
    print("[2/4] Selecting picks ...", file=sys.stderr)
    picks = select.select_picks(candidates, max_picks=args.max_picks)
    if not select.is_enough(picks):
        print(
            f"[skip] only {len(picks)} repos passed delta>={config.MIN_DELTA_THRESHOLD}; "
            f"min is {config.MIN_PICKS}",
            file=sys.stderr,
        )
        return 0
    print(f"       picked {len(picks)} repos", file=sys.stderr)

    # 3. Summarize
    provider = "none" if args.no_ai else args.provider
    print(f"[3/4] Summarizing (provider={provider or config.SUMMARIZER_PROVIDER}) ...",
          file=sys.stderr)
    try:
        summarizer = summarize.get_summarizer(provider)
    except RuntimeError as exc:
        print(f"[fail] summarizer init: {exc}", file=sys.stderr)
        return 2
    summaries = summarize.summarize_all(picks, summarizer)

    # 4. Render
    print("[4/4] Rendering markdown ...", file=sys.stderr)
    print("", file=sys.stderr)
    print(render.render_markdown(picks, summaries, mode=args.mode))
    return 0


if __name__ == "__main__":
    sys.exit(main())
