#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# OpenClaw 容器启动脚本
#
# 职责:
#   1. 配置初始化 - 从模板生成 openclaw.json（首次 / 强制重建）
#   2. 凭证注入   - 将环境变量中的凭证写入文件
#   3. 缓存清理   - 清理 jiti 编译缓存
#   4. 前台启动   - exec 让 Node.js 成为 PID 1，接收 K8s SIGTERM
#
# 注意: 不依赖 apt 包，用 node 替代 envsubst
# =============================================================================

OPENCLAW_DIR="/root/.openclaw"
CONFIG_FILE="${OPENCLAW_DIR}/openclaw.json"
TEMPLATE_FILE="${OPENCLAW_DIR}/openclaw.json.template"
CREDENTIALS_DIR="${OPENCLAW_DIR}/credentials"

# ---- 1. 配置初始化 ----

# 用 node 实现 envsubst（替换模板中的 ${VAR} 占位符）
envsubst_node() {
  node -e "
    const fs = require('fs');
    let t = fs.readFileSync('$1', 'utf8');
    t = t.replace(/\\\$\{([^}]+)\}/g, (_, k) => process.env[k] ?? '');
    fs.writeFileSync('$2', t);
  "
}

# 设置默认值
export OPENCLAW_GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-18789}"
export OPENCLAW_GATEWAY_BIND="${OPENCLAW_GATEWAY_BIND:-lan}"
export OPENCLAW_LOG_LEVEL="${OPENCLAW_LOG_LEVEL:-info}"

# 未指定 Token 时自动生成一个随机 Token
if [ -z "${OPENCLAW_GATEWAY_TOKEN:-}" ]; then
  OPENCLAW_GATEWAY_TOKEN=$(node -e "console.log(require('crypto').randomBytes(24).toString('hex'))")
  export OPENCLAW_GATEWAY_TOKEN
  echo "[entrypoint] =================================================="
  echo "[entrypoint] 未指定 OPENCLAW_GATEWAY_TOKEN，已自动生成"
  echo "[entrypoint] Token: ${OPENCLAW_GATEWAY_TOKEN}"
  echo "[entrypoint]"
  echo "[entrypoint] 打开控制台: http://localhost:${OPENCLAW_GATEWAY_PORT}/?token=${OPENCLAW_GATEWAY_TOKEN}"
  echo "[entrypoint]"
  echo "[entrypoint] 如需固定 Token，启动时加 -e OPENCLAW_GATEWAY_TOKEN=<你的Token>"
  echo "[entrypoint] =================================================="
fi

if [ "${OPENCLAW_FORCE_RECONFIG:-false}" = "true" ]; then
  echo "[entrypoint] OPENCLAW_FORCE_RECONFIG=true，从模板重新生成配置..."
  if [ -f "${TEMPLATE_FILE}" ]; then
    envsubst_node "${TEMPLATE_FILE}" "${CONFIG_FILE}"
    echo "[entrypoint] 配置已重新生成: ${CONFIG_FILE}"
  else
    echo "[entrypoint] 警告: 模板文件不存在 ${TEMPLATE_FILE}，跳过配置生成"
  fi
elif [ ! -f "${CONFIG_FILE}" ]; then
  echo "[entrypoint] 首次启动，从模板生成配置..."
  if [ -f "${TEMPLATE_FILE}" ]; then
    envsubst_node "${TEMPLATE_FILE}" "${CONFIG_FILE}"
    echo "[entrypoint] 配置已生成: ${CONFIG_FILE}"
  else
    echo "[entrypoint] 警告: 模板文件不存在 ${TEMPLATE_FILE}，将以无配置模式启动"
  fi
else
  echo "[entrypoint] 配置文件已存在，跳过生成"
fi

# ---- 2. 凭证注入 ----

if [ -n "${OPENCLAW_CREDENTIALS_JSON:-}" ]; then
  mkdir -p "${CREDENTIALS_DIR}"
  echo "${OPENCLAW_CREDENTIALS_JSON}" > "${CREDENTIALS_DIR}/default.json"
  echo "[entrypoint] 凭证已写入: ${CREDENTIALS_DIR}/default.json"
fi

# ---- 3. 清理编译缓存 ----

rm -rf /tmp/jiti/* 2>/dev/null || true

# ---- 4. 前台启动 ----

echo "[entrypoint] 启动 OpenClaw Gateway..."
echo "[entrypoint]   端口: ${OPENCLAW_GATEWAY_PORT}"
echo "[entrypoint]   绑定: ${OPENCLAW_GATEWAY_BIND}"
echo "[entrypoint]   日志级别: ${OPENCLAW_LOG_LEVEL}"

# exec 替换当前 shell 进程，让 Node.js 成为 PID 1
exec openclaw gateway --allow-unconfigured --bind lan
