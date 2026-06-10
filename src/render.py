"""Render the picked repos as Markdown or as a copy-friendly HTML page."""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from premailer import transform

from . import config
from .models import RepoMeta

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

ASSETS_DIR = Path(__file__).resolve().parent.parent / "docs" / "assets"
STYLE_CSS_PATH = ASSETS_DIR / "style.css"


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


# -------- HTML rendering (used by docs/today.html etc.) --------


def render_html_body(
    picks: list[RepoMeta],
    summaries: dict[str, str],
    *,
    mode: str = "daily",
    now: datetime | None = None,
    tags: dict[str, str] | None = None,
) -> str:
    """Render the digest content as class-tagged HTML (NOT inlined).

    `tags` is `{full_name: tag_text}` for optional badges (e.g. weekly mode
    "新晋" / "延续 热度").
    """
    now = now or datetime.now(config.TIMEZONE)
    weekday = WEEKDAY_CN[now.weekday()]
    total_delta = sum(repo.stars_today for repo in picks)
    tags = tags or {}

    if mode == "weekly":
        title = f"GitHub 周报 · 第 {now.isocalendar().week} 周"
    else:
        title = f"GitHub 日报 · {now.month}月{now.day}日（{weekday}）"

    parts = [
        '<section class="digest-root">',
        f'<h1 class="digest-title">{escape(title)}</h1>',
        f'<p class="digest-summary">📌 今日 {len(picks)} 个仓库,共新增 ⭐ {_fmt_int(total_delta)}</p>',
        '<hr class="digest-sep">',
    ]

    for i, repo in enumerate(picks, start=1):
        summary = summaries.get(repo.full_name) or repo.description or ""
        tag = tags.get(repo.full_name)
        meta_bits = [f'<span class="repo-meta-bit">📈 +{_fmt_int(repo.stars_today)} ⭐</span>']
        if repo.language:
            meta_bits.append(f'<span class="repo-meta-bit">🔧 {escape(repo.language)}</span>')
        if repo.topics:
            meta_bits.append(f'<span class="repo-meta-bit">🏷️ {escape(repo.topics[0])}</span>')
        meta_html = "".join(meta_bits)

        tag_html = f'<span class="tag">{escape(tag)}</span> ' if tag else ""

        parts.append(
            f'<h3 class="repo-header">'
            f'<span class="repo-num">{i}</span>'
            f'{tag_html}'
            f'<span class="repo-name">{escape(repo.full_name)}</span>'
            f'</h3>'
        )
        parts.append(f'<p class="repo-desc">{escape(summary)}</p>')
        parts.append(f'<p class="repo-meta">{meta_html}</p>')
        parts.append(
            f'<p class="repo-link">🔗 <a href="{escape(repo.url)}">{escape(repo.url)}</a></p>'
        )
        if i < len(picks):
            parts.append('<hr class="repo-sep">')

    parts.append('<hr class="digest-sep">')
    parts.append(
        f'<p class="digest-footer">'
        f'📅 本期生成时间: {now.strftime("%Y-%m-%d %H:%M")}<br>'
        f'💡 数据来源: GitHub Trending'
        f'</p>'
    )
    parts.append("</section>")
    return "\n".join(parts)


def inline_css(html_body: str, css_path: Path | None = None) -> str:
    """Inline CSS from `css_path` (default: docs/assets/style.css) into HTML.

    premailer scans <style> tags + the body and produces `style=""` on each
    matching element. Required for WeChat editor compatibility.
    """
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
    # Extract body inner — premailer keeps the wrapper.
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
  body {{
    margin: 0;
    background: #f0f2f5;
    font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif;
  }}
  .page-frame {{
    max-width: 677px;
    margin: 0 auto;
    background: #fff;
    min-height: 100vh;
  }}
  .copy-bar {{
    position: sticky;
    top: 0;
    z-index: 10;
    background: #fff;
    border-bottom: 1px solid #e2e8f0;
    padding: 12px 16px;
    text-align: center;
  }}
  .copy-btn {{
    width: 100%;
    max-width: 360px;
    min-height: 48px;
    font-size: 16px;
    font-weight: 600;
    color: #fff;
    background: #07c160;
    border: none;
    border-radius: 6px;
    padding: 12px 16px;
    cursor: pointer;
  }}
  .copy-btn:active {{
    background: #06a050;
  }}
  .copy-btn[data-state="ok"] {{
    background: #2c3e50;
  }}
  .copy-btn[data-state="err"] {{
    background: #c0392b;
  }}
  .content-host {{
    padding: 16px;
  }}
  .hint {{
    color: #a0aec0;
    font-size: 12px;
    margin-top: 4px;
  }}
</style>
</head>
<body>
<div class="page-frame">
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


def render_full_page(
    picks: list[RepoMeta],
    summaries: dict[str, str],
    *,
    mode: str = "daily",
    now: datetime | None = None,
    tags: dict[str, str] | None = None,
) -> str:
    """Render the complete standalone HTML page (with copy button + inlined body)."""
    now = now or datetime.now(config.TIMEZONE)
    weekday = WEEKDAY_CN[now.weekday()]
    if mode == "weekly":
        title = f"GitHub 周报 · 第 {now.isocalendar().week} 周"
    else:
        title = f"GitHub 日报 · {now.month}月{now.day}日（{weekday}）"

    body_html = render_html_body(picks, summaries, mode=mode, now=now, tags=tags)
    inlined = inline_css(body_html)
    return PAGE_TEMPLATE.format(title=escape(title), body=inlined)
