#!/bin/bash
# Nanobot 版本检测脚本
#
# 查询 PyPI 上 nanobot-ai 的最新稳定版本，与 Dockerfile 中的当前版本对比。
# 仅采纳"干净"的正式版本（X.Y.Z 格式），排除 .devN、.postN、aN、bN、rcN 等后缀。
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

CURRENT=$(sed -n 's/^ARG NANOBOT_VERSION=//p' "${DOCKERFILE}")
if [ -z "${CURRENT}" ]; then
  echo "错误: 无法从 Dockerfile 读取 NANOBOT_VERSION"
  exit 1
fi

echo "当前版本: ${CURRENT}"
echo "查询 PyPI registry..."

LATEST=$(curl -sS https://pypi.org/pypi/nanobot-ai/json | python3 -c "
import json, sys, re
data = json.load(sys.stdin)
versions = list(data['releases'].keys())
stable = [v for v in versions if re.match(r'^\d+\.\d+\.\d+$', v)]
stable.sort(key=lambda v: list(map(int, v.split('.'))))
print(stable[-1] if stable else '')
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
echo "  PyPI:      https://pypi.org/project/nanobot-ai/${LATEST}/"
echo "=========================================="

if [ "${UPDATE}" = true ]; then
  echo ""
  echo "更新 Dockerfile..."
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/ARG NANOBOT_VERSION=${CURRENT}/ARG NANOBOT_VERSION=${LATEST}/" "${DOCKERFILE}"
    sed -i '' "s/ARG IMAGE_VERSION=v${CURRENT}/ARG IMAGE_VERSION=v${LATEST}/" "${DOCKERFILE}"
  else
    sed -i "s/ARG NANOBOT_VERSION=${CURRENT}/ARG NANOBOT_VERSION=${LATEST}/" "${DOCKERFILE}"
    sed -i "s/ARG IMAGE_VERSION=v${CURRENT}/ARG IMAGE_VERSION=v${LATEST}/" "${DOCKERFILE}"
  fi
  echo "Dockerfile 已更新: ${CURRENT} -> ${LATEST}"
  echo ""
  echo "后续步骤:"
  echo "  1. git add nodeskclaw-artifacts/nanobot-image/Dockerfile"
  echo "  2. git commit -m \"chore(nanobot): 升级 Nanobot 至 ${LATEST}\""
  echo "  3. cd nodeskclaw-artifacts/nanobot-image && ./build-and-push.sh --version ${LATEST}"
else
  echo ""
  echo "如需自动更新 Dockerfile，运行:"
  echo "  $0 --update"
  echo ""
  echo "或手动构建指定版本:"
  echo "  cd nodeskclaw-artifacts/nanobot-image && ./build-and-push.sh --version ${LATEST}"
fi
