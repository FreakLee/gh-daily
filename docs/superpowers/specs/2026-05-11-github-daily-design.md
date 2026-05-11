# GitHub 日报/周报 公众号半自动推送系统 · 设计文档

- **项目代号**：`gh-daily`
- **设计日期**：2026-05-11
- **作者**：FIRE-Lee + Claude
- **目标读者**：未来实现者（你本人 / AI 助手）

---

## 1. 项目目标

每天早上 8 点（北京时间）、周一至周四，向你推送一份「GitHub 前一日热门仓库榜单」；每周五早上 8 点推送一份「本周综合热门榜单（周报）」。内容以中文资讯形式整理，最终发布到你的微信公众号。

### 1.1 核心约束

- 公众号是**未认证个人订阅号**，无群发图文 API 权限，因此必须走「半自动」路径：程序自动生成内容 + 你手动一键发布。
- 不需要花钱（包括 AI 服务）。
- 你 Mac 不必常开机，运行环境需独立于本地。
- 起步即可用，工程量可控。

### 1.2 成功标准

- 周一至周四，每天 8 点（±10 分钟）手机收到推送，点击链接打开预览页，点一个按钮复制内容，粘贴到公众号后台，30 秒内可发布。
- 周五同样流程，但内容形态切换为周报视角。
- 失败/跳过日不发布垃圾内容；通过显式通知告知原因。

---

## 2. 整体架构

### 2.1 一句话定位

一个跑在 GitHub Actions 上的 Python 项目，每天/每周自动抓 GitHub Trending、用 GitHub Models 写中文简介、生成排版好的预览页面，并通过 Bark 推送链接到你手机；你点开预览页 → 一键复制 → 粘贴到公众号后台 → 发布。

### 2.2 仓库结构

```
gh-daily/                          # 一个 private GitHub repo
├── .github/workflows/
│   ├── daily.yml                  # 周一~周四 08:00 CST 触发
│   └── weekly.yml                 # 周五 08:00 CST 触发
├── src/
│   ├── __init__.py
│   ├── fetch.py                   # 抓 GitHub Trending + Search API
│   ├── snapshot.py                # star 数快照入库 + 算增量
│   ├── select.py                  # 排序、去重、弹性数量决策
│   ├── summarize.py               # 中文简介生成 (provider 无关接口)
│   ├── render.py                  # Markdown + HTML 双输出
│   ├── notify.py                  # Bark 推送
│   ├── config.py                  # 所有可调旋钮
│   └── main.py                    # 编排入口, 参数化 daily/weekly
├── data/
│   ├── snapshots.db               # SQLite, 存每日 star 快照
│   ├── history.json               # 已推送过的仓库 + 发期记录
│   └── run-log.jsonl              # 每次跑的结果日志 (skip/fail/ok)
├── docs/                          # GitHub Pages 根目录
│   ├── index.html                 # 首页: 历史期列表
│   ├── today.html                 # 最新一期 (每次覆盖)
│   ├── archive/                   # 每期 HTML 永久归档
│   │   └── YYYY-MM-DD.html
│   └── assets/
│       ├── style.css              # 公众号风格样式 (源)
│       └── icon.png               # Bark 推送图标
├── tests/
│   ├── test_select.py
│   ├── test_snapshot.py
│   └── test_render.py
├── pyproject.toml
└── README.md
```

### 2.3 端到端数据流（daily 模式一次完整运行）

```
[GH Actions cron: 周一~四 08:00 北京时间 / 00:00 UTC]
       ↓
 1. fetch.py 抓取:
       · github.com/trending HTML 解析 (~25 个全球榜仓库)
       · GitHub Search API (created:>过去 30 天, stars:>50, 补充冷启动新仓库)
       ↓
 2. snapshot.py:
       · 把今天所有候选仓库的元数据写入 SQLite snapshots 表
       · 和昨天/前几天的快照对比, 算出「今日新增 star」
       ↓
 3. select.py:
       · 按今日 star 增量降序
       · 排除 history.json 里 7 天内推送过的
       · 取 top N (N=5~10, 弹性: star 增量 >50 才入选)
       · 若入选数 < MIN_PICKS=3 → skip 当天, 不发文
       ↓
 4. summarize.py:
       · 对入选仓库串行调用 AI (默认 GitHub Models / gpt-4o-mini)
       · 输入: name / description / topics / language / stars
       · 输出: 30~60 字中文卖点描述
       ↓
 5. render.py:
       · 拼装 Markdown (人类可读的源)
       · 渲染 HTML, 用 premailer 把外部 CSS 全部内联
       · 覆盖 docs/today.html, 复制到 docs/archive/YYYY-MM-DD.html
       · 更新 docs/index.html 历史列表
       ↓
 6. git commit + push 把所有产物入库
       (含 SQLite、history.json、HTML、run-log)
       ↓
 7. notify.py: 调 Bark API 推送
       title: "GitHub 日报 · 5月12日 已就绪"
       body : "今日 7 个仓库, 共新增 ⭐ 12.3k"
       url  : "https://<user>.github.io/gh-daily/today.html"
       group: "gh-daily"
```

**Weekly 模式（周五 08:00）**：调用 `main.py --mode weekly`，分支走「周综合」逻辑（详见 §4.3），其余流程完全复用。

### 2.4 关键架构取舍

- **状态持久化用 git commit 回 repo**：不依赖外部数据库；代价是 repo 慢慢长大（每天几 KB，多年可控）。
- **GitHub Pages 用同 repo 的 `docs/` 目录托管**：零额外配置，免费 CDN，URL 稳定。
- **预览页直接复制富文本**：用 `Clipboard API` 同时写入 `text/html` 和 `text/plain`，公众号编辑器接收 HTML 部分以获得完整排版。
- **AI provider 抽象接口**：`summarize.py` 定义 `Summarizer` 抽象类，默认实现是 `GitHubModelsSummarizer`，预留 `ClaudeSummarizer` 一行配置切换。

---

## 3. 数据存储

### 3.1 SQLite Schema (`data/snapshots.db`)

```sql
CREATE TABLE snapshots (
    snapshot_date  TEXT NOT NULL,          -- 'YYYY-MM-DD', 北京时区
    repo_full_name TEXT NOT NULL,          -- 'owner/repo'
    stars          INTEGER NOT NULL,       -- 当时的总 star 数
    description    TEXT,                   -- 抓取时的英文 description
    language       TEXT,
    topics         TEXT,                   -- JSON 数组字符串
    source         TEXT NOT NULL,          -- 'trending' | 'search' | 'both'
    PRIMARY KEY (snapshot_date, repo_full_name)
);

CREATE INDEX idx_repo_date ON snapshots(repo_full_name, snapshot_date);
```

设计说明：
- 主键 `(snapshot_date, repo_full_name)` 保证同一天同一仓库只一条，重跑幂等。
- `description / language / topics` 随快照存历史值，便于复盘和应对原仓库描述更改。
- 不存 README（形态 1 精简榜单不需要深度内容）。

### 3.2 推送历史 (`data/history.json`)

```json
{
  "issues": [
    {
      "date": "2026-05-12",
      "mode": "daily",
      "repos": ["facebook/react", "rust-lang/rust"],
      "url": "https://lyman.github.io/gh-daily/archive/2026-05-12.html"
    },
    {
      "date": "2026-05-15",
      "mode": "weekly",
      "repos": ["..."],
      "url": "..."
    }
  ]
}
```

去重时遍历最近 `DEDUP_WINDOW_DAYS=7` 天，排除已出现过的 repo。

### 3.3 运行日志 (`data/run-log.jsonl`)

每次跑追加一行 JSON：

```json
{"ts":"2026-05-12T00:03:21Z","mode":"daily","status":"ok","picks":7,"top_delta":1247}
{"ts":"2026-05-13T00:02:55Z","mode":"daily","status":"skip","reason":"入选不足 3 个"}
{"ts":"2026-05-14T00:04:11Z","mode":"daily","status":"fail","reason":"trending 解析失败 + search 429"}
```

便于将来扒模式（跳过频率、失败类型）。

---

## 4. 关键算法

### 4.1 算法 A：今日 star 增量

```
delta_today(repo) = stars(today) - stars(most_recent_snapshot_before_today)
```

**边界处理**：

- 仓库**首次出现**（无历史快照）→ delta 设为「当天 trending 第一名的 delta」，让新仓库有机会被选中，避免被埋。
- 上次快照是 N 天前（如周末未跑） → 直接用最近一条历史快照差值，不做日均归一。因为人为增长经常爆发式，归一反而失真。

### 4.2 算法 B：当日选片

```python
candidates = fetch_all()  # ~25 trending + ~30 search 去重后约 40~50 个

# 1. 写快照
for repo in candidates:
    db.upsert_snapshot(today, repo)

# 2. 算增量 + 过滤
scored = []
for repo in candidates:
    delta = compute_delta(repo)
    if delta < MIN_DELTA_THRESHOLD:    # 50, 过滤"在榜但不涨"
        continue
    if repo.full_name in recent_history(days=DEDUP_WINDOW_DAYS):
        continue                       # 7 天内发过的跳过
    scored.append((delta, repo))

scored.sort(reverse=True)
selected = scored[:MAX_PICKS]          # 10

# 3. 弹性数量
if len(selected) < MIN_PICKS:          # 3
    return SkipResult("入选不足 3 个, 改日再发")
```

可调旋钮（`config.py`）：`MIN_DELTA_THRESHOLD=50`、`MAX_PICKS=10`、`MIN_PICKS=3`、`DEDUP_WINDOW_DAYS=7`。

### 4.3 算法 C：周五周报聚合

```python
window = db.snapshots_in_range(today - WEEKLY_WINDOW_DAYS, today)  # 7 天

weekly_delta = {}
for repo in unique_repos(window):
    earliest = min(s.stars for s in window if s.repo == repo)
    latest   = max(s.stars for s in window if s.repo == repo)
    weekly_delta[repo] = latest - earliest

top10 = sorted(weekly_delta.items(), key=lambda x: -x[1])[:10]

# 标签判定
for repo, delta in top10:
    appearances_in_window = count_in_window(repo, window)
    in_previous_issues    = repo in any_previous_issue(within_days=30)

    if not in_previous_issues:
        tag = "🆕 本周新晋"
    elif appearances_in_window >= 5:
        tag = "🔥 延续热度"
    else:
        tag = None
```

**注意**：周报**不读 history.json 做去重** —— 即使日报介绍过的仓库，本周持续在涨也值得在周报回顾，仅标注「延续热度」。

### 4.4 GitHub Trending HTML 解析鲁棒性

GitHub Trending 无官方 API，靠爬 HTML。两个保险：

1. **CSS 选择器版本化**：`fetch.py` 里的选择器作为常量集中放一处，将来 GitHub 改版只改一个文件。
2. **抓取失败兜底**：trending 抓不到时，仅用 GitHub Search API 的结果。两个都失败才返回 skip。

---

## 5. 内容形态与渲染

### 5.1 每条仓库字段（形态 1：精简榜单）

```
[序号] 仓库名（owner/repo）
[一句中文简介,AI 生成,30~60 字]
📈 今日新增 ⭐ 1.2k    🔧 主语言    🏷️ 主要 topic
🔗 https://github.com/owner/repo
```

### 5.2 AI 简介生成

**默认 provider**：GitHub Models / `gpt-4o-mini`，通过 `actions/ai-inference` 或直接调用 `https://models.inference.ai.azure.com/chat/completions`，认证用 `GITHUB_TOKEN` + `models: read` 权限。

**Prompt 模板**（中文输出，要求 30~60 字）：

```
你是技术资讯编辑。给定一个 GitHub 仓库的元数据,用 30~60 字
中文写一句卖点描述,突出 "解决什么问题 + 亮点"。
不要重复仓库名,不要用"这是一个"这种废话开头。

仓库: {owner}/{repo}
描述: {description}
主语言: {language}
Topics: {topics}
当前 star 数: {stars}
今日新增 star: {delta}
```

**Provider 抽象**（`summarize.py`）：

```python
class Summarizer(Protocol):
    def summarize(self, repo: RepoMeta) -> str: ...

class GitHubModelsSummarizer:
    def __init__(self, model="gpt-4o-mini", token=...): ...
    def summarize(self, repo) -> str: ...

class ClaudeSummarizer:
    def __init__(self, model="claude-haiku-4-5-20251001", api_key=...): ...
    def summarize(self, repo) -> str: ...

# main.py
SUMMARIZER_MAP = {
    "github_models": GitHubModelsSummarizer,
    "claude": ClaudeSummarizer,
}
summarizer = SUMMARIZER_MAP[config.SUMMARIZER_PROVIDER](
    model=config.SUMMARIZER_MODEL
)
```

切换 provider 只需改 `config.py` 一行。

### 5.3 HTML 渲染管线

```
Markdown 源
  ↓ markdown-it-py 解析 (启用 GFM 插件)
HTML (带 class)
  ↓ premailer 把外部 CSS 内联到每个标签的 style 属性
HTML (全内联样式)
  ↓ 嵌入到 today.html 模板的 #content-to-copy div
最终 today.html
```

**为什么内联 CSS**：公众号编辑器接收富文本粘贴时仅识别行内 `style` 属性，不识别外部 CSS 类。

### 5.4 预览页结构 (`today.html`)

```
┌─────────────────────────────────────┐
│ [📋 复制富文本(用于公众号)]  ← sticky │
├─────────────────────────────────────┤
│                                     │
│   GitHub 日报 · 5月12日 (周一)     │
│   今日 7 个仓库,共新增 ⭐ 12.3k     │
│                                     │
│   1. owner/repo-name                │
│      [一句中文卖点]                  │
│      📈 +1.2k ⭐  🔧 Rust  🏷️ cli    │
│      🔗 https://github.com/...      │
│                                     │
│   2. ...                            │
│                                     │
│   ────────────────────              │
│   📅 本期生成时间: 08:00            │
│   💡 数据来源: GitHub Trending     │
└─────────────────────────────────────┘
```

移动优先（单列、字号 16px+、按钮 44pt 高）。从 Bark 通知打开多半在 iPhone 上。

### 5.5 「复制富文本」按钮实现

```html
<button id="copy-btn">📋 复制富文本(用于公众号)</button>
<div id="content-to-copy"><!-- 全内联样式 HTML --></div>

<script>
document.getElementById('copy-btn').addEventListener('click', async () => {
  const content = document.getElementById('content-to-copy');
  try {
    await navigator.clipboard.write([
      new ClipboardItem({
        'text/html':  new Blob([content.innerHTML], {type: 'text/html'}),
        'text/plain': new Blob([content.innerText], {type: 'text/plain'})
      })
    ]);
    alert('已复制,直接粘贴到公众号编辑器');
  } catch (e) {
    alert('复制失败, 请长按选中页面内容手动复制');
  }
});
</script>
```

### 5.6 归档与索引

- `docs/today.html`：每次覆盖，永远是最新一期。
- `docs/archive/YYYY-MM-DD.html`：每期归档，永久 URL。
- `docs/index.html`：自动生成的索引页，倒序列出所有历史期。

---

## 6. 通知 (Bark)

### 6.1 调用形式

```
POST https://api.day.app/<DEVICE_KEY>
{
  "title": "GitHub 日报 · 5月12日 已就绪",
  "body":  "今日 7 个仓库,共新增 ⭐ 12.3k",
  "url":   "https://lyman.github.io/gh-daily/today.html",
  "icon":  "https://lyman.github.io/gh-daily/assets/icon.png",
  "group": "gh-daily",
  "level": "active"
}
```

`DEVICE_KEY` 存 GitHub repo secret。

### 6.2 三种通知场景

| 场景 | title | body | level |
|---|---|---|---|
| 正常发布 | `GitHub 日报 · MM月DD日 已就绪` | `今日 N 个仓库,共新增 ⭐ X` | `active` |
| 跳过 | `GitHub 日报 · MM月DD日 已跳过` | `原因: <跳过原因>` | `passive` |
| 失败 | `GitHub 日报 · MM月DD日 失败` | `错误: <错误摘要>` | `critical` |

### 6.3 周报通知差异

```
title: "GitHub 周报 · 第 W 周 已就绪"
body : "本周 Top 10, 含 N 个新晋黑马"
group: "gh-daily-weekly"   # 与日报独立折叠
```

---

## 7. 错误处理

整体原则：**宁可跳过，不发垃圾**。

| 失败场景 | 处理 |
|---|---|
| Trending HTML 解析失败 | 降级用 Search API；都失败 → skip + Bark 通知 |
| Search API 429/超时 | 重试 3 次、指数退避；仍失败 → 只用 trending |
| SQLite 写入失败 | abort，Actions 标红 |
| AI 单条调用失败 | 该条用 description 机翻兜底（不阻断全期） |
| AI 全部失败 | 全篇用英文 description 兜底，Bark 文案加 ⚠️ |
| 入选不足 MIN_PICKS | skip + Bark 通知 |
| git push 失败 | Actions 标红；不重发 Bark（避免假阳性） |
| Bark 推送失败 | Actions 标红；HTML 仍可通过 Pages 看到 |

所有 skip/fail 都写一行到 `run-log.jsonl`，commit 入库。

---

## 8. 测试策略

不追求覆盖率，专注两类高价值测试：

### 8.1 单元测试（pytest）

- `test_select.py`：传入 fake snapshots，验证选片结果（边界、阈值、去重窗口）。
- `test_snapshot.py`：delta 计算的边界（首次出现、跨多天、并列）。
- `test_render.py`：给定 fixture 数据，验证 HTML 含关键字段且通过 premailer 内联。

### 8.2 端到端 dry-run

```bash
python -m src.main --mode daily --dry-run
```

真抓数据、真调 AI、**不写库不发推送不 commit**，只在终端打印渲染结果。本地能跑通 = 基本能上 Actions。

### 8.3 不写的测试

- 不 mock GitHub Trending HTML（脆性高，维护成本不值）—— 集成验证靠每周一次手动 dry-run。
- 不 mock Bark（直接发到测试 group 看到就行）。

---

## 9. 配置项一览 (`config.py`)

```python
TIMEZONE             = "Asia/Shanghai"
MIN_DELTA_THRESHOLD  = 50         # 单期入选最低 star 增量
MAX_PICKS            = 10         # 单期最多仓库数
MIN_PICKS            = 3          # 不足则 skip
DEDUP_WINDOW_DAYS    = 7          # 几天内推过的不再推
WEEKLY_WINDOW_DAYS   = 7
SEARCH_API_DAYS      = 30         # search "created:>过去 N 天"
SEARCH_API_MIN_STARS = 50

SUMMARIZER_PROVIDER  = "github_models"   # "github_models" | "claude"
SUMMARIZER_MODEL     = "gpt-4o-mini"
SUMMARIZER_MAX_CHARS = 60

BARK_GROUP_DAILY     = "gh-daily"
BARK_GROUP_WEEKLY    = "gh-daily-weekly"

PAGES_BASE_URL       = "https://<your-gh-username>.github.io/gh-daily"
```

---

## 10. 启动里程碑

**M1 - 离线生成版（1~2 晚）**
- 本地能跑：抓数据 → 算增量 → AI 简介 → 输出 markdown 到 stdout
- 不存数据、不发推送、不生成 HTML
- 验收：肉眼看输出，5 个仓库的中文简介质量过关

**M2 - 持久化 + HTML（半天）**
- 加 SQLite 快照、history.json
- 加 HTML 渲染 + 公众号样式 + 复制按钮
- 本地浏览器打开 today.html，肉眼检查排版
- 验收：把 today.html 的复制结果手动粘贴到公众号后台「写新文章」，排版正常

**M3 - GitHub Actions + Pages + Bark（半天）**
- 推到 GitHub private repo，开 Pages，配 Actions secrets
- 手动触发 workflow 一次
- 验收：手机收到 Bark 推送 → 点击进入 Pages → 按按钮成功复制 → 粘贴到公众号后台

**M4 - 定时 + 周报（一晚）**
- 加 cron schedule
- 实现 weekly.yml + 周报聚合逻辑
- 验收：连续观察一周，每天/每周五准点（±10 分钟）收到通知

---

## 11. 明确不做的（YAGNI）

- ❌ 仓库按语言/分类的多个频道（先全球榜单频道跑顺再说）
- ❌ AI 翻译 README 内容（形态 1 不需要）
- ❌ 自动生成封面图（手动选张代码截图就行）
- ❌ 阅读量/订阅数等数据回流（未认证号拿不到分析 API）
- ❌ 多人订阅 / RSS 输出
- ❌ Web UI 改配置（直接改 `config.py`）
- ❌ Docker 化

---

## 12. 一句话总结

约 800 行 Python 的 GitHub Actions 项目，每日凌晨抓 GitHub Trending + Search 数据，用 GitHub Models（免费）生成中文卖点，渲染成公众号风格的 HTML 预览页托管在 GitHub Pages，通过 Bark 推送提醒你打开预览页一键复制粘贴到公众号后台发布。周五自动切换到周综合视角。失败/不够料就跳过，不发垃圾。
