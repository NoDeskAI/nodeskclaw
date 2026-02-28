#!/bin/bash
# OpenClaw 版本检测脚本
#
# 查询 npm 上 OpenClaw 的最新稳定版本，与 Dockerfile 中的当前版本对比。
# 仅采纳"干净"的正式版本（YYYY.M.DD 格式），排除 -beta、-rc、-1、-2 等后缀。
#
# 用法:
#   ./check-update.sh            # 检查是否有新版本
#   ./check-update.sh --update   # 检查并自动更新 Dockerfile
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCKERFILE="${SCRIPT_DIR}/Dockerfile"
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

CURRENT=$(sed -n 's/^ARG OPENCLAW_VERSION=//p' "${DOCKERFILE}")
if [ -z "${CURRENT}" ]; then
  echo "错误: 无法从 Dockerfile 读取 OPENCLAW_VERSION"
  exit 1
fi

echo "当前版本: ${CURRENT}"
echo "查询 npm registry..."

ALL_VERSIONS=$(npm view openclaw versions --json 2>/dev/null)
if [ -z "${ALL_VERSIONS}" ]; then
  echo "错误: 无法查询 npm registry"
  exit 1
fi

# 过滤: 只保留 YYYY.M.DD 格式的正式版本（排除 -beta、-rc、-1、-2 等后缀）
LATEST=$(echo "${ALL_VERSIONS}" | node -e "
  const versions = JSON.parse(require('fs').readFileSync('/dev/stdin', 'utf8'));
  const stable = versions.filter(v => /^\d{4}\.\d{1,2}\.\d{1,2}$/.test(v));
  if (stable.length > 0) console.log(stable[stable.length - 1]);
")

if [ -z "${LATEST}" ]; then
  echo "错误: 未找到符合条件的稳定版本"
  exit 1
fi

echo "最新稳定版: ${LATEST}"

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
echo "  Release:   https://github.com/openclaw/openclaw/releases/tag/v${LATEST}"
echo "=========================================="

if [ "${UPDATE}" = true ]; then
  echo ""
  echo "更新 Dockerfile..."
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/ARG OPENCLAW_VERSION=${CURRENT}/ARG OPENCLAW_VERSION=${LATEST}/" "${DOCKERFILE}"
    sed -i '' "s/ARG IMAGE_VERSION=v${CURRENT}/ARG IMAGE_VERSION=v${LATEST}/" "${DOCKERFILE}"
  else
    sed -i "s/ARG OPENCLAW_VERSION=${CURRENT}/ARG OPENCLAW_VERSION=${LATEST}/" "${DOCKERFILE}"
    sed -i "s/ARG IMAGE_VERSION=v${CURRENT}/ARG IMAGE_VERSION=v${LATEST}/" "${DOCKERFILE}"
  fi
  echo "Dockerfile 已更新: ${CURRENT} -> ${LATEST}"
  echo ""
  echo "后续步骤:"
  echo "  1. git add nodeskclaw-artifacts/openclaw-image/Dockerfile"
  echo "  2. git commit -m \"chore(openclaw): 升级 OpenClaw 至 ${LATEST}\""
  echo "  3. cd nodeskclaw-artifacts/openclaw-image && ./build-and-push.sh"
else
  echo ""
  echo "如需自动更新 Dockerfile，运行:"
  echo "  $0 --update"
  echo ""
  echo "或手动构建指定版本:"
  echo "  cd nodeskclaw-artifacts/openclaw-image && ./build-and-push.sh --version ${LATEST}"
fi
