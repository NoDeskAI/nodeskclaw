#!/bin/bash
# ZeroClaw 版本检测脚本
#
# 查询 GitHub Releases 上 ZeroClaw 的最新版本，与 Dockerfile 中的当前版本对比。
# 仅采纳非预发布的正式 Release。
#
# 前提: 需要 gh CLI 并已登录（用于 GitHub API 认证）
#
# 用法:
#   ./check-update.sh            # 检查是否有新版本
#   ./check-update.sh --update   # 检查并自动更新 Dockerfile
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCKERFILE="${SCRIPT_DIR}/Dockerfile"
GITHUB_REPO="nicholasgasior/zeroclaw"
UPDATE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --update)
      UPDATE=true
      shift
      ;;
    *)
      echo "未知参数: $1"
      echo "用法: $0 [--update]"
      exit 1
      ;;
  esac
done

CURRENT=$(sed -n 's/^ARG ZEROCLAW_VERSION=//p' "${DOCKERFILE}")
if [ -z "${CURRENT}" ]; then
  echo "错误: 无法从 Dockerfile 读取 ZEROCLAW_VERSION"
  exit 1
fi

echo "当前版本: ${CURRENT}"
echo "查询 GitHub Releases (${GITHUB_REPO})..."

LATEST=$(gh api "repos/${GITHUB_REPO}/releases/latest" --jq '.tag_name' 2>/dev/null || echo "")

if [ -z "${LATEST}" ]; then
  echo "错误: 无法获取最新 release（仓库可能不存在、无 release、或 gh 未认证）"
  exit 1
fi

echo "最新版本: ${LATEST}"

if [ "${CURRENT}" = "${LATEST}" ]; then
  echo ""
  echo "已是最新版本，无需更新。"
  exit 0
fi

echo ""
echo "=========================================="
echo "  发现新版本!"
echo "=========================================="
echo "  当前版本:  ${CURRENT}"
echo "  最新版本:  ${LATEST}"
echo "  Release:   https://github.com/${GITHUB_REPO}/releases/tag/${LATEST}"
echo "=========================================="

if [ "${UPDATE}" = true ]; then
  echo ""
  echo "更新 Dockerfile..."
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/ARG ZEROCLAW_VERSION=${CURRENT}/ARG ZEROCLAW_VERSION=${LATEST}/" "${DOCKERFILE}"
    sed -i '' "s/ARG IMAGE_VERSION=${CURRENT}/ARG IMAGE_VERSION=${LATEST}/" "${DOCKERFILE}"
  else
    sed -i "s/ARG ZEROCLAW_VERSION=${CURRENT}/ARG ZEROCLAW_VERSION=${LATEST}/" "${DOCKERFILE}"
    sed -i "s/ARG IMAGE_VERSION=${CURRENT}/ARG IMAGE_VERSION=${LATEST}/" "${DOCKERFILE}"
  fi
  echo "Dockerfile 已更新: ${CURRENT} -> ${LATEST}"
  echo ""
  echo "后续步骤:"
  echo "  1. git add nodeskclaw-artifacts/zeroclaw-image/Dockerfile"
  echo "  2. git commit -m \"chore(zeroclaw): 升级 ZeroClaw 至 ${LATEST}\""
  echo "  3. cd nodeskclaw-artifacts/zeroclaw-image && ./build-and-push.sh --version ${LATEST}"
else
  echo ""
  echo "如需自动更新 Dockerfile，运行:"
  echo "  $0 --update"
  echo ""
  echo "或手动构建指定版本:"
  echo "  cd nodeskclaw-artifacts/zeroclaw-image && ./build-and-push.sh --version ${LATEST}"
fi
