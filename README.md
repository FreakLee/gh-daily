# gh-daily

多源科技/AI + 财经资讯,每日打包成中文榜单,通过半自动流程发布到公众号。

两条独立日报:

- **科技 / AI 日报**：GitHub Trending + Hacker News + Hugging Face Daily Papers + arXiv
- **财经晨报**：华尔街见闻 + CNBC + MarketWatch + 美联储官方,并对涉及特朗普/马斯克/黄仁勋/鲍威尔等关键政商人物的条目加权置顶(「靠新闻反向捞言论」)

完整设计见 [`docs/superpowers/specs/2026-05-11-github-daily-design.md`](docs/superpowers/specs/2026-05-11-github-daily-design.md)。

---

## 当前进度

- ✅ **多源管线**：泛化 `Item` 模型 + `sources/` 插件式取数 + 每源配额选片 + 分类 prompt + 两条日报独立产出
- ✅ SQLite 快照(GitHub star 增量) + 分类 history 去重 + HTML 渲染 + 复制按钮
- ⬜ GitHub Actions + Pages + Bark
- ⬜ 定时 + 周报

---

## 本地运行（M1）

### 1. 准备环境

```bash
cd gh-daily
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. 配置 GitHub Token（用于 AI 简介）

1. 打开 https://github.com/settings/tokens
2. **Generate new token (classic)**，勾选 `models:read` scope
3. 复制 token，写入 `.env`：

```bash
cp .env.example .env
# 编辑 .env，填入 GITHUB_TOKEN=ghp_xxxxx
```

### 3. 跑起来

```bash
# 完整模式（两条日报都生成,用 GitHub Models 写中文要点）
python -m src.main

# 只跑某一条
python -m src.main --category tech
python -m src.main --category finance

# 不调 AI（跳过 AI,只看管道是否通；所有取数源都免 key）
python -m src.main --no-ai --dry-run
```

产物写到 `docs/<category>/today.html`(+ archive)，根索引 `docs/index.html` 链接两条线。
Markdown 同步打到 stdout，日志走 stderr。

---

## 文件结构

```
src/
├── config.py            # 所有可调旋钮(分类/配额/RSS 源/人物关键词)
├── models.py            # 通用 Item dataclass
├── sources/             # 插件式取数,每源一个文件,统一 fetch() -> list[Item]
│   ├── base.py          # Source 协议 + HTTP helper
│   ├── github.py        # GitHub Trending
│   ├── hackernews.py    # HN Algolia
│   ├── huggingface.py   # HF Daily Papers
│   ├── arxiv.py         # arXiv cs.AI/cs.CL/cs.LG
│   └── rss.py           # 通用 RSS(财经源 + 美联储)+ 人物关键词加权
├── select.py            # 每源配额选片
├── summarize.py         # 分类 prompt(科技 / 财经),Provider 抽象 + chat()
├── illustrate.py        # 封面配图:LLM 生成提示词 → Draw Things 本地出图
├── snapshot.py          # GitHub star 增量快照
├── history.py           # 分类去重
├── render.py            # Markdown + 公众号 HTML 双输出
└── main.py              # CLI 入口,按分类编排
```

---

## 调旋钮（`src/config.py`）

- `TECH_SOURCE_QUOTAS` / `FINANCE_SOURCE_QUOTAS`：每源占多少条(注释掉一行即下线该源)
- `SOURCE_MIN_SCORE`：各源入选的最低热度(star 增量 / HN 分 / 论文赞)
- `RSS_FEEDS`：财经 RSS 源列表,加一个源 = 加一行
- `FIGURE_KEYWORDS` / `FIGURE_BOOST`：政商人物关键词与加权强度
- `MIN_PICKS = 3`：单期不足则跳过
- `SUMMARIZER_PROVIDER = "github_models"`：可改 `claude` 或 `none`

### 封面配图(Draw Things,本地)

每期可自动生成一张封面图嵌到文首:LLM 根据当期头条写英文画面提示词(配 `COVER_STYLE_SUFFIX` 固定风格)→ POST 到 Draw Things 本地 API 出图 → 以 data-uri 嵌入,并另存 `docs/<分类>/today.png` 方便手动设为公众号封面。

启用前提(否则自动跳过、不影响发布):
1. 打开 Draw Things,选好模型
2. 设置里**开启 API Server**(默认端口 7860)
3. 正常跑 `python -m src.main` 即可;临时不出图加 `--no-image`

旋钮在 `config.py`:`ENABLE_COVER_IMAGE`、`COVER_POSITION`(head/foot)、尺寸、`COVER_STYLE_SUFFIX`、`DRAWTHINGS_ENDPOINT`。

> ⚠️ 配图依赖本地 Draw Things,只能本地跑,无法在云端 GitHub Actions 出图。微信编辑器对粘贴图片处理不稳定,最稳是用 `today.png` 手动设为封面。

### 加一个新数据源

1. 在 `src/sources/` 写个新文件,实现 `fetch() -> list[Item]`
2. 在 `sources/__init__.py` 注册
3. 在对应分类的 `*_SOURCE_QUOTAS` 里给它配额
