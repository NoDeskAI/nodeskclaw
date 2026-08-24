#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# OpenClaw 实例镜像集成验证脚本
#
# 用法: ./verify.sh <image:tag>
# 示例: ./verify.sh registry.example.com/deskclaw/deskclaw-openclaw:v2026.3.28
#
# 验证项:
#   1. 容器启动不 crash
#   2. 配置兼容性（写入标准配置后进程存活）
#   3. 目录结构完整
#   4. CLI 参数可用
#   5. Gateway 端口监听
#   6. 版本标记正确
# =============================================================================

IMAGE="${1:?用法: $0 <image:tag>}"
CONTAINER_NAME="verify-openclaw-$(date +%s)"
PASS=0
FAIL=0
CHECKS=()

pass() { PASS=$((PASS+1)); CHECKS+=("PASS: $1"); echo "  ✓ $1"; }
fail() { FAIL=$((FAIL+1)); CHECKS+=("FAIL: $1 — $2"); echo "  ✗ $1: $2"; }

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "=== 验证镜像: $IMAGE ==="
echo ""

# ---------- 1. 启动验证 ----------
echo "[1/6] 容器启动"

if ! docker run -d --name "$CONTAINER_NAME" --platform linux/amd64 \
    -e OPENCLAW_GATEWAY_TOKEN=verify-test-token \
    "$IMAGE" >/dev/null 2>&1; then
  fail "容器启动" "docker run 失败"
  echo ""; echo "=== 验证中止 ==="; exit 1
fi

sleep 5

STATE=$(docker inspect --format='{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "missing")
if [ "$STATE" = "running" ]; then
  pass "容器启动正常 (status=$STATE)"
else
  EXIT_CODE=$(docker inspect --format='{{.State.ExitCode}}' "$CONTAINER_NAME" 2>/dev/null || echo "?")
  fail "容器启动" "status=$STATE, exit_code=$EXIT_CODE"
  echo "--- 容器日志 ---"
  docker logs --tail=30 "$CONTAINER_NAME" 2>&1 || true
  echo ""; echo "=== 验证中止 ==="; exit 1
fi

# ---------- 2. 配置兼容性 ----------
echo "[2/6] 配置兼容性"

CONFIG_CHECK=$(docker exec "$CONTAINER_NAME" node -e "
  const fs = require('fs');
  try {
    const text = fs.readFileSync('/root/.openclaw/openclaw.json', 'utf8').replace(/^\s*\/\/.*$/gm, '');
    const c = JSON.parse(text);
    if (c.gateway && c.gateway.auth && c.gateway.auth.token) {
      console.log('OK');
    } else {
      console.log('MISSING_GATEWAY_AUTH');
    }
  } catch (e) {
    console.log('PARSE_ERROR: ' + e.message);
  }
" 2>&1)

if [ "$CONFIG_CHECK" = "OK" ]; then
  pass "openclaw.json 解析正常，gateway.auth.token 存在"
else
  fail "配置兼容性" "$CONFIG_CHECK"
fi

# ---------- 3. 目录结构 ----------
echo "[3/6] 目录结构"

DIRS_TO_CHECK=(
  "/root/.openclaw"
  "/root/.openclaw/openclaw.json"
  "/root/.openclaw/openclaw.json.template"
)

ALL_DIRS_OK=true
for d in "${DIRS_TO_CHECK[@]}"; do
  if ! docker exec "$CONTAINER_NAME" test -e "$d" 2>/dev/null; then
    fail "目录结构" "缺失: $d"
    ALL_DIRS_OK=false
  fi
done
if $ALL_DIRS_OK; then
  pass "目录结构完整 (${#DIRS_TO_CHECK[@]} 项)"
fi

# ---------- 4. CLI 参数 ----------
echo "[4/6] CLI 参数"

HELP_OUTPUT=$(docker exec "$CONTAINER_NAME" openclaw gateway --help 2>&1 || echo "CLI_ERROR")
if echo "$HELP_OUTPUT" | grep -q "\-\-bind"; then
  pass "openclaw gateway --help 包含 --bind 参数"
else
  fail "CLI 参数" "--bind 参数未找到"
fi

if echo "$HELP_OUTPUT" | grep -q "\-\-allow-unconfigured"; then
  pass "openclaw gateway --help 包含 --allow-unconfigured 参数"
else
  fail "CLI 参数" "--allow-unconfigured 参数未找到"
fi

# ---------- 5. 端口监听 ----------
echo "[5/6] 端口监听"

sleep 3

GW_CHECK=$(docker exec "$CONTAINER_NAME" sh -c 'wget -q -O /dev/null --timeout=3 http://127.0.0.1:18789/healthz 2>&1 && echo OK || echo FAIL' 2>&1)
if echo "$GW_CHECK" | grep -q "OK"; then
  pass "Gateway 端口 18789 可达 (/healthz)"
else
  fail "端口监听" "18789/healthz 不可达: $GW_CHECK"
fi

SSE_CHECK=$(docker exec "$CONTAINER_NAME" sh -c 'ss -tlnp 2>/dev/null | grep 9721 || netstat -tlnp 2>/dev/null | grep 9721 || echo NOT_LISTENING' 2>&1)
if echo "$SSE_CHECK" | grep -q "9721"; then
  pass "SSE 端口 9721 监听中"
else
  fail "端口监听" "9721 未监听: $SSE_CHECK"
fi

# ---------- 6. 版本标记 ----------
echo "[6/6] 版本标记"

VERSION_FILE=$(docker exec "$CONTAINER_NAME" cat /root/.openclaw-version 2>/dev/null || echo "NOT_FOUND")
if [ "$VERSION_FILE" != "NOT_FOUND" ] && [ -n "$VERSION_FILE" ]; then
  pass "版本标记: $VERSION_FILE"
else
  fail "版本标记" "/root/.openclaw-version 不存在或为空"
fi

# ---------- 汇总 ----------
echo ""
echo "=== 验证完成 ==="
echo "  PASS: $PASS"
echo "  FAIL: $FAIL"
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo "失败项:"
  for c in "${CHECKS[@]}"; do
    if [[ "$c" == FAIL* ]]; then
      echo "  - $c"
    fi
  done
  exit 1
fi

echo "全部通过"
exit 0
