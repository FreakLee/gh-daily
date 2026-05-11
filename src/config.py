"""Centralized configuration. Tweak these knobs after observing real runs."""

from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Asia/Shanghai")

# Selection knobs
MIN_DELTA_THRESHOLD = 50
MAX_PICKS = 10
MIN_PICKS = 3
DEDUP_WINDOW_DAYS = 7
WEEKLY_WINDOW_DAYS = 7

# Fetcher knobs (M2+ uses Search API; M1 only uses Trending)
TRENDING_URL = "https://github.com/trending"
TRENDING_TIMEOUT_SECONDS = 15
HTTP_USER_AGENT = "gh-daily/0.1 (+https://github.com/)"

# Summarizer knobs
SUMMARIZER_PROVIDER = "github_models"   # "github_models" | "claude" | "none"
SUMMARIZER_GH_MODEL = "gpt-4o-mini"        # 免费档限流宽松;DeepSeek-V3 中文好但限流严(1/分钟)
SUMMARIZER_CLAUDE_MODEL = "claude-haiku-4-5-20251001"
SUMMARIZER_MAX_CHARS = 60
SUMMARIZER_TIMEOUT_SECONDS = 30

# GitHub Models endpoint (OpenAI-compatible)
GH_MODELS_ENDPOINT = "https://models.inference.ai.azure.com/chat/completions"

# Bark (used from M3)
BARK_BASE = "https://api.day.app"
BARK_GROUP_DAILY = "gh-daily"
BARK_GROUP_WEEKLY = "gh-daily-weekly"
