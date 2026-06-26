"""Render picked items as Markdown or a copy-friendly HTML page (per category)."""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from premailer import transform

from . import config
from .models import Item

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

ASSETS_DIR = Path(__file__).resolve().parent.parent / "docs" / "assets"
STYLE_CSS_PATH = ASSETS_DIR / "style.css"


def _truncate(text: str, limit: int) -> str:
    """Safety net so a runaway title/blurb (e.g. an arXiv abstract used as
    fallback) never blows up the layout. AI summaries are already short and stay
    well under these caps."""
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _title(category: str, now: datetime) -> str:
    base = config.CATEGORY_TITLES.get(category, "资讯")
    weekday = WEEKDAY_CN[now.weekday()]
    return f"{base} · {now.month}月{now.day}日（{weekday}）"


def issue_title(category: str, now: datetime) -> str:
    """Public accessor for the issue title (used by the WeChat draft module)."""
    return _title(category, now)


def _sources_line(items: list[Item]) -> str:
    seen = []
    for it in items:
        label = it.source_label or it.source
        if label not in seen:
            seen.append(label)
    return "、".join(seen)


# Section header icon per source (picks come grouped by source).
SOURCE_ICONS = {
    "github": "🐙", "hackernews": "🟧", "huggingface": "🤗", "arxiv": "📄",
    "rss:sspai": "📱", "rss:36kr": "💼", "rss:ifanr": "📲", "rss:solidot": "👾",
    "rss:wallstreetcn": "📈", "rss:cnbc": "🏦", "rss:yahoo": "💹", "rss:fed": "🏛️",
}


def _section_title(item: Item) -> str:
    icon = SOURCE_ICONS.get(item.source, "📰")
    return f"{icon} {item.source_label or item.source}"


def render_markdown(items: list[Item], *, category: str, now: datetime | None = None) -> str:
    now = now or datetime.now(config.TIMEZONE)
    title = _title(category, now)

    lines = [
        f"# {title}",
        "",
        f"📌 今日 {len(items)} 条 · 来源 {_sources_line(items)}",
        "",
        "---",
        "",
    ]
    for i, item in enumerate(items, start=1):
        meta_bits = [_section_title(item), item.metric_label, *item.tags]
        meta = "    ".join(b for b in meta_bits if b)
        lines.extend([
            f"**{i}. {_truncate(item.display_title, config.TITLE_MAX_CHARS)}**",
            "",
            _truncate(item.display_summary, config.SUMMARY_MAX_CHARS),
            "",
            meta,
            "",
            f"🔗 {item.url}",
            "",
            "---",
            "",
        ])
    lines.extend([
        f"📅 本期生成时间: {now.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"💡 数据来源: {_sources_line(items)}",
    ])
    return "\n".join(lines)


# -------- HTML rendering --------


def _cover_html(cover_data_uri: str | None) -> str:
    if not cover_data_uri:
        return ""
    return (
        f'<p class="cover" style="margin:0 0 16px 0;text-align:center;">'
        f'<img src="{cover_data_uri}" alt="" '
        f'style="width:100%;max-width:100%;border-radius:10px;display:block;"></p>'
    )


def render_html_body(
    items: list[Item],
    *,
    category: str,
    now: datetime | None = None,
    cover_data_uri: str | None = None,
) -> str:
    """Render the digest content as class-tagged HTML (NOT inlined)."""
    now = now or datetime.now(config.TIMEZONE)
    title = _title(category, now)

    parts = [
        f'<section class="digest-root {escape(category)}">',
        f'<h1 class="digest-title">{escape(title)}</h1>',
        f'<p class="digest-summary"><span class="digest-summary-pill">'
        f'📌 今日 {len(items)} 条 · {escape(_sources_line(items))}</span></p>',
    ]
    if config.COVER_POSITION == "head":
        parts.append(_cover_html(cover_data_uri))
    parts.append('<hr class="digest-sep">')
    for i, item in enumerate(items, start=1):
        meta_html = f'<span class="repo-source">{escape(_section_title(item))}</span>'
        if item.metric_label:
            meta_html += f'<span class="repo-metric">{escape(item.metric_label)}</span>'
        meta_html += "".join(
            f'<span class="repo-meta-bit">{escape(t)}</span>' for t in item.tags if t
        )
        parts.append(
            f'<h3 class="repo-header">'
            f'<span class="repo-num">{i}</span>'
            f'<span class="repo-name">{escape(_truncate(item.display_title, config.TITLE_MAX_CHARS))}</span>'
            f'</h3>'
        )
        parts.append(
            f'<p class="repo-desc">{escape(_truncate(item.display_summary, config.SUMMARY_MAX_CHARS))}</p>'
        )
        parts.append(f'<p class="repo-meta">{meta_html}</p>')
        parts.append(
            f'<p class="repo-link">🔗 <a href="{escape(item.url)}">{escape(item.url)}</a></p>'
        )
        if i < len(items):
            parts.append('<hr class="repo-sep">')

    parts.append('<hr class="digest-sep">')
    if config.COVER_POSITION == "foot":
        parts.append(_cover_html(cover_data_uri))
    parts.append(
        f'<p class="digest-footer">'
        f'📅 本期生成时间: {now.strftime("%Y-%m-%d %H:%M")}<br>'
        f'💡 数据来源: {escape(_sources_line(items))}'
        f'</p>'
    )
    parts.append("</section>")
    return "\n".join(parts)


def inline_css(html_body: str, css_path: Path | None = None) -> str:
    """Inline CSS into HTML (required for WeChat editor compatibility)."""
    css_path = css_path or STYLE_CSS_PATH
    css = css_path.read_text(encoding="utf-8")
    document = f'<!DOCTYPE html><html><head><style>{css}</style></head><body>{html_body}</body></html>'
    inlined = transform(
        document,
        keep_style_tags=False,
        remove_classes=False,
        strip_important=False,
        disable_validation=True,
    )
    start = inlined.find("<body>") + len("<body>")
    end = inlined.rfind("</body>")
    return inlined[start:end].strip()


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>{title}</title>
<style>
  :root {{ --accent: {accent}; --accent-dark: {accent_dark}; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: #eef0f3;
    font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif;
  }}
  .page-frame {{
    max-width: 677px;
    margin: 0 auto;
    background: #fff;
    min-height: 100vh;
    box-shadow: 0 0 24px rgba(0,0,0,0.06);
  }}
  .top-band {{
    background: linear-gradient(135deg, var(--accent), var(--accent-dark));
    color: #fff;
    padding: 18px 20px 16px;
  }}
  .top-band .kicker {{ font-size: 12px; opacity: 0.85; letter-spacing: 2px; }}
  .top-band .brand {{ font-size: 19px; font-weight: 800; margin-top: 4px; }}
  .copy-bar {{
    position: sticky;
    top: 0;
    z-index: 10;
    background: rgba(255,255,255,0.92);
    backdrop-filter: saturate(180%) blur(8px);
    border-bottom: 1px solid #e8ebef;
    padding: 12px 16px;
    text-align: center;
  }}
  .copy-btn {{
    width: 100%;
    max-width: 380px;
    min-height: 50px;
    font-size: 16px;
    font-weight: 700;
    color: #fff;
    background: #07c160;
    border: none;
    border-radius: 25px;
    padding: 13px 16px;
    cursor: pointer;
    box-shadow: 0 4px 14px rgba(7,193,96,0.32);
    transition: transform .05s ease;
  }}
  .copy-btn:active {{ background: #06a050; transform: translateY(1px); }}
  .copy-btn[data-state="ok"] {{ background: var(--accent); box-shadow: none; }}
  .copy-btn[data-state="err"] {{ background: #c0392b; box-shadow: none; }}
  .content-host {{ padding: 20px 18px 32px; }}
  .hint {{ color: #94a3b8; font-size: 12px; margin-top: 8px; }}
</style>
</head>
<body>
<div class="page-frame">
  <div class="top-band">
    <div class="kicker">GH-DAILY</div>
    <div class="brand">{title}</div>
  </div>
  <div class="copy-bar">
    <button id="copy-btn" class="copy-btn">📋 复制富文本(用于公众号)</button>
    <div class="hint">复制后切换到公众号后台「写新文章」编辑器,粘贴即可</div>
  </div>
  <div class="content-host">
    <div id="content-to-copy">{body}</div>
  </div>
</div>
<script>
(function() {{
  const btn = document.getElementById('copy-btn');
  btn.addEventListener('click', async () => {{
    const node = document.getElementById('content-to-copy');
    const html = node.innerHTML;
    const text = node.innerText;
    try {{
      await navigator.clipboard.write([
        new ClipboardItem({{
          'text/html': new Blob([html], {{type: 'text/html'}}),
          'text/plain': new Blob([text], {{type: 'text/plain'}})
        }})
      ]);
      btn.textContent = '✅ 已复制,去公众号粘贴';
      btn.dataset.state = 'ok';
    }} catch (e) {{
      btn.textContent = '⚠️ 复制失败,请长按手动选';
      btn.dataset.state = 'err';
      console.error(e);
    }}
    setTimeout(() => {{
      btn.textContent = '📋 复制富文本(用于公众号)';
      btn.dataset.state = '';
    }}, 3000);
  }});
}})();
</script>
</body>
</html>
"""


# Preview-shell accent per category (browser-only; the pasted body uses style.css).
ACCENTS = {
    "tech": ("#0071e3", "#0058b9"),     # Apple blue
    "finance": ("#d93025", "#b3261e"),  # 红(国内财经语境)
}


def render_full_page(
    items: list[Item],
    *,
    category: str,
    now: datetime | None = None,
    cover_data_uri: str | None = None,
) -> str:
    """Render the complete standalone HTML page (copy button + inlined body)."""
    now = now or datetime.now(config.TIMEZONE)
    body_html = render_html_body(items, category=category, now=now, cover_data_uri=cover_data_uri)
    inlined = inline_css(body_html)
    accent, accent_dark = ACCENTS.get(category, ("#3182ce", "#2b6cb0"))
    return PAGE_TEMPLATE.format(
        title=escape(_title(category, now)),
        body=inlined,
        accent=accent,
        accent_dark=accent_dark,
    )


def render_inlined_body(items: list[Item], *, category: str, now: datetime | None = None) -> str:
    """Inlined content body only (no page shell, no cover image) — for WeChat draft.

    The cover goes in as the WeChat 封面/thumb separately; data-uri images don't
    survive the WeChat editor, so we never embed it in the content here.
    """
    now = now or datetime.now(config.TIMEZONE)
    return inline_css(render_html_body(items, category=category, now=now))
