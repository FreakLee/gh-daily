"""Centralized configuration. Tweak these knobs after observing real runs."""

from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Asia/Shanghai")

# ---------------------------------------------------------------------------
# Categories & per-source quotas
# ---------------------------------------------------------------------------
# Each category produces one independent issue (科技/AI 日报, 财经晨报).
# Cross-source heat (GitHub stars vs HN points vs PH votes vs RSS recency) is
# not comparable, so we DON'T globally normalize — instead each source gets a
# fixed slot count and ranks only within itself. Order here is render order.

CATEGORIES = ["tech", "finance"]

CATEGORY_TITLES = {
    "tech": "AI科技日报",
    "finance": "财经晨报",
}

# source_key -> slots in the issue. Comment out a line to drop a source.
TECH_SOURCE_QUOTAS = {
    "github": 3,
    "hackernews": 3,
    "huggingface": 2,
    "arxiv": 1,
    "rss:sspai": 2,      # 少数派:工具/效率/认知
    "rss:36kr": 1,       # 36氪:创投/商业科技
    # "rss:ifanr": 2,    # 爱范儿:消费数码(默认关闭,取消注释即启用)
    # "rss:solidot": 2,  # Solidot:极客新闻
}

FINANCE_SOURCE_QUOTAS = {
    "rss:wallstreetcn": 4,   # 华尔街见闻 (中文实时财经)
    "rss:cnbc": 3,
    "rss:yahoo": 2,          # Yahoo财经:市场/公司/人物
    "rss:fed": 1,            # 美联储官方:FOMC/主席原文
}

# Minimum within-source heat to be eligible (0 = no floor). RSS sources have no
# numeric heat so they rely on recency + the figure-keyword boost below.
SOURCE_MIN_SCORE = {
    "github": 50,        # daily star delta
    "hackernews": 80,    # HN points
    "huggingface": 0,    # paper upvotes (accumulate through the day)
    "arxiv": 0,
}

MIN_PICKS = 3            # per issue; below this we skip the issue
DEDUP_WINDOW_DAYS = 7
WEEKLY_WINDOW_DAYS = 7

# ---------------------------------------------------------------------------
# Tech sources
# ---------------------------------------------------------------------------
TRENDING_URL = "https://github.com/trending"
HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
HN_HITS = 30
HF_DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"
HF_LIMIT = 30
ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_CATEGORIES = ["cs.CL", "cs.AI", "cs.LG"]
ARXIV_MAX_RESULTS = 30

# ---------------------------------------------------------------------------
# Finance sources (RSS, no API key needed)
# ---------------------------------------------------------------------------
# key -> (display name, feed url, category, translate_title).
# translate_title=True 让英文标题被 AI 译成中文;中文源设 False。
# Add a feed = add a line here and give it a quota slot.
RSS_FEEDS = {
    # ---- finance ----
    "rss:wallstreetcn": ("华尔街见闻", "https://dedicated.wallstreetcn.com/rss.xml", "finance", False),
    "rss:cnbc": ("CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "finance", True),
    "rss:yahoo": ("Yahoo财经", "https://finance.yahoo.com/news/rssindex", "finance", True),
    "rss:fed": ("美联储", "https://www.federalreserve.gov/feeds/press_all.xml", "finance", True),
    # ---- tech (中国大陆媒体,均为官方原生 RSS) ----
    "rss:sspai": ("少数派", "https://sspai.com/feed", "tech", False),
    "rss:36kr": ("36氪", "https://www.36kr.com/feed", "tech", False),
    "rss:ifanr": ("爱范儿", "https://www.ifanr.com/feed", "tech", False),
    "rss:solidot": ("Solidot", "https://www.solidot.org/index.rss", "tech", False),
    # 机器之心/量子位无官方 RSS,需自建 RSSHub:rsshub.app/jiqizhixin、rsshub.app/qbitai
}
RSS_MAX_AGE_HOURS = 36   # ignore items older than this
RSS_PER_FEED = 25        # parse at most this many items per feed

# "言论反向捞":当一条财经新闻提到这些关键政商人物时,加权重并打标签,
# 因为他们的发言常常左右市场。命中即 score += FIGURE_BOOST。
FIGURE_KEYWORDS = {
    "特朗普": ["trump", "特朗普"],
    "马斯克": ["musk", "马斯克"],
    "黄仁勋": ["jensen huang", "nvidia ceo", "黄仁勋"],
    "沃什": ["warsh", "沃什"],            # 现任美联储主席(2026-05 上任,接替鲍威尔)
    "美联储": ["powell", "fomc", "federal reserve", "鲍威尔", "美联储"],  # 机构 + 前主席
    "贝森特": ["bessent", "贝森特"],
    "拉加德": ["lagarde", "ecb", "拉加德"],
}
FIGURE_BOOST = 100.0     # large enough to float figure-mentions to the top

# ---------------------------------------------------------------------------
# Shared HTTP
# ---------------------------------------------------------------------------
HTTP_TIMEOUT_SECONDS = 15
HTTP_USER_AGENT = "gh-daily/0.2 (+https://github.com/)"

# ---------------------------------------------------------------------------
# Summarizer
# ---------------------------------------------------------------------------
SUMMARIZER_PROVIDER = "deepseek"   # "deepseek" | "github_models" | "claude" | "none"
SUMMARIZER_GH_MODEL = "gpt-4o-mini"
SUMMARIZER_CLAUDE_MODEL = "claude-haiku-4-5-20251001"
SUMMARIZER_MAX_CHARS = 60
SUMMARIZER_TIMEOUT_SECONDS = 30
GH_MODELS_ENDPOINT = "https://models.inference.ai.azure.com/chat/completions"

# DeepSeek (OpenAI-compatible). `deepseek-chat` 始终指向最新对话模型(当前 V 系列),
# 无需手动追版本号;如要钉死某版可改成具体 id。
SUMMARIZER_DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"

# Display length caps (safety net; AI output already obeys the prompt length).
TITLE_MAX_CHARS = 80
SUMMARY_MAX_CHARS = 100

# ---------------------------------------------------------------------------
# Cover image — generated locally via Draw Things (its A1111-compatible HTTP API).
# Local-only: if Draw Things isn't running / API server is off, the run logs a
# warning and continues without an image. Toggle off entirely with --no-image.
# In Draw Things: enable the API Server (default port 7860) and pick a model.
# ---------------------------------------------------------------------------
ENABLE_COVER_IMAGE = True
COVER_POSITION = "head"               # "head"(文首) | "foot"(文末)
DRAWTHINGS_ENDPOINT = "http://127.0.0.1:7860/sdapi/v1/txt2img"
COVER_WIDTH = 1024
COVER_HEIGHT = 576                     # 16:9, 适合文首横幅
COVER_STEPS = 20
COVER_TIMEOUT_SECONDS = 180           # 本地出图可能较慢
# 固定风格后缀:LLM 只描述画面主体,风格由这里统一,保证每期视觉一致(品牌感)。
COVER_STYLE_SUFFIX = {
    "tech": "clean modern editorial illustration, abstract tech concept, soft blue gradient, "
            "minimal geometric shapes, generous negative space, flat design, high quality",
    "finance": "sleek editorial illustration, abstract financial market motif, deep red and gold accents, "
               "minimal, professional, generous negative space, flat design, high quality",
}
COVER_NEGATIVE_PROMPT = ("text, words, letters, typography, watermark, signature, logo, "
                         "low quality, blurry, jpeg artifacts, ugly, deformed, cluttered, "
                         "retro, vintage, 1990s, 2000s, CRT monitor, boxy monitor, beige computer, "
                         "old technology, steam train, locomotive, gears, cogwheels, light bulb, "
                         "robot, human brain, circuit board cliche, dated")

# ---------------------------------------------------------------------------
# WeChat 公众号 草稿 API (本地运行,--draft)
# ---------------------------------------------------------------------------
# AppID/AppSecret 从 .env 读(WECHAT_APPID / WECHAT_APPSECRET)。
# 前提:账号已认证有接口权限,且把本机公网 IP 加入「IP 白名单」(获取 access_token 必需)。
# 草稿必须有封面图(thumb),所以 --draft 时需要 Draw Things 生成的封面;若拿不到封面则跳过该条。
WECHAT_AUTHOR = "FIRE-Lee"             # 草稿署名,改成你的笔名
WECHAT_TOKEN_ENDPOINT = "https://api.weixin.qq.com/cgi-bin/token"
WECHAT_MATERIAL_ENDPOINT = "https://api.weixin.qq.com/cgi-bin/material/add_material"
WECHAT_DRAFT_ENDPOINT = "https://api.weixin.qq.com/cgi-bin/draft/add"
WECHAT_TIMEOUT_SECONDS = 60

# ---------------------------------------------------------------------------
# Bark (used from M3)
# ---------------------------------------------------------------------------
BARK_BASE = "https://api.day.app"
BARK_GROUPS = {
    "tech": "gh-daily-tech",
    "finance": "gh-daily-finance",
}
