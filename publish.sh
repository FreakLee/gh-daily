#!/usr/bin/env bash
# 一键发布:触发云端生成今天内容 → 等跑完 → 拉取 → 出封面 + 建公众号草稿。
#
# 用法:
#   ./publish.sh            # 科技 + 财经 两条都做
#   ./publish.sh tech       # 只做科技
#   ./publish.sh finance    # 只做财经
#
# 前提:
#   - gh 已登录;.env 配好 DEEPSEEK_API_KEY 和 WECHAT_APPID/WECHAT_APPSECRET
#   - 本机当前公网 IP 在公众号 IP 白名单里(不确定先跑 .venv/bin/python -m src.wechat)
#   - Draw Things 开着 API Server 并加载了模型(草稿必须有封面)
set -euo pipefail
cd "$(dirname "$0")"

CAT_ARG=""
[ "${1:-}" != "" ] && CAT_ARG="--category $1"

echo "▶ 1/4 触发云端生成今天内容 ..."
gh workflow run daily.yml
sleep 6
RUN_ID=$(gh run list --workflow=daily.yml --limit 1 --json databaseId -q '.[0].databaseId')

echo "▶ 2/4 等待云端跑完 (run $RUN_ID,约 1 分钟) ..."
gh run watch "$RUN_ID" --exit-status --interval 15 >/dev/null

echo "▶ 3/4 拉取最新内容 ..."
git pull --no-edit

echo "▶ 4/4 出封面 + 建公众号草稿(确保 Draw Things 已开)..."
.venv/bin/python -m src.main $CAT_ARG --draft-only

echo "✅ 完成。打开公众号 App → 草稿箱 → 发布。"
