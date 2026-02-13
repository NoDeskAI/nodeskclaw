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
# =============================================================================

OPENCLAW_DIR="/root/.openclaw"
CONFIG_FILE="${OPENCLAW_DIR}/openclaw.json"
TEMPLATE_FILE="${OPENCLAW_DIR}/openclaw.json.template"
CREDENTIALS_DIR="${OPENCLAW_DIR}/credentials"

# ---- 1. 配置初始化 ----

# 设置 envsubst 占位符的默认值（环境变量未设置时用这些）
export OPENCLAW_GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-18789}"
export OPENCLAW_GATEWAY_BIND="${OPENCLAW_GATEWAY_BIND:-lan}"
export OPENCLAW_GATEWAY_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-}"
export OPENCLAW_LOG_LEVEL="${OPENCLAW_LOG_LEVEL:-info}"

if [ "${OPENCLAW_FORCE_RECONFIG:-false}" = "true" ]; then
  # 强制重建：从模板重新生成配置（用于配置更新场景）
  echo "[entrypoint] OPENCLAW_FORCE_RECONFIG=true，从模板重新生成配置..."
  if [ -f "${TEMPLATE_FILE}" ]; then
    envsubst < "${TEMPLATE_FILE}" > "${CONFIG_FILE}"
    echo "[entrypoint] 配置已重新生成: ${CONFIG_FILE}"
  else
    echo "[entrypoint] 警告: 模板文件不存在 ${TEMPLATE_FILE}，跳过配置生成"
  fi
elif [ ! -f "${CONFIG_FILE}" ]; then
  # 首次部署：配置文件不存在，从模板生成
  echo "[entrypoint] 首次启动，从模板生成配置..."
  if [ -f "${TEMPLATE_FILE}" ]; then
    envsubst < "${TEMPLATE_FILE}" > "${CONFIG_FILE}"
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
# K8s 发 SIGTERM 时进程能正确接收并优雅关闭
exec openclaw gateway --allow-unconfigured --bind lan
