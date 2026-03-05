#!/usr/bin/env bash
set -euo pipefail

EE_REPO="git@github.com:NoDeskAI/nodeskclaw-ee.git"
EE_DIR="$(cd "$(dirname "$0")/.." && pwd)/ee"

if [ -d "$EE_DIR/.git" ]; then
  echo "ee/ 已存在且是 git 仓库，执行 git pull ..."
  cd "$EE_DIR" && git pull
  exit 0
fi

if [ -d "$EE_DIR" ] && [ "$(ls -A "$EE_DIR" 2>/dev/null)" ]; then
  echo "错误：ee/ 目录已存在且非空，但不是 git 仓库。请手动处理后重试。"
  exit 1
fi

echo "正在克隆 EE 仓库到 ee/ ..."
git clone "$EE_REPO" "$EE_DIR"
echo "完成。重启后端服务即可启用 EE 模式。"
