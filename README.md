# gh-daily

把 GitHub Trending 每日/每周打包成中文榜单，通过半自动流程发布到公众号。

完整设计见 [`docs/superpowers/specs/2026-05-11-github-daily-design.md`](docs/superpowers/specs/2026-05-11-github-daily-design.md)。

---

## 当前进度

- ✅ **M1（离线生成版）**：抓 Trending → 选 top-N → AI 中文卖点 → 输出 Markdown 到 stdout
- ⬜ M2：SQLite 快照 + HTML 渲染 + 复制按钮
- ⬜ M3：GitHub Actions + Pages + Bark
- ⬜ M4：定时 + 周报

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
# 完整模式（用 GitHub Models 生成中文简介）
python -m src.main

# 不调 AI（跳过简介,只看管道是否通）
python -m src.main --no-ai

# 限制数量,便于快速看输出
python -m src.main --max-picks 3
```

输出是 Markdown 到 stdout，过滤日志走 stderr。把它重定向到文件：

```bash
python -m src.main > today.md 2> run.log
```

---

## 文件结构

```
src/
├── config.py        # 所有可调旋钮
├── models.py        # RepoMeta dataclass
├── fetch.py         # Trending HTML scraper
├── select.py        # 排序 / 阈值 / top-N
├── summarize.py     # 中文简介,Provider 抽象
├── render.py        # Markdown 输出
└── main.py          # CLI 入口
```

---

## 调旋钮

所有可调参数在 `src/config.py`：

- `MIN_DELTA_THRESHOLD = 50`：单期入选最低 star 增量
- `MAX_PICKS = 10`：单期最多仓库数
- `MIN_PICKS = 3`：不足则跳过
- `SUMMARIZER_PROVIDER = "github_models"`：可改 `claude` 或 `none`
- `SUMMARIZER_MAX_CHARS = 60`：简介最长 60 字
