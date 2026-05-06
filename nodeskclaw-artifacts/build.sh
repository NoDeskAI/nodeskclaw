#!/bin/bash
# build.sh — DeskClaw 统一镜像构建入口
#
# 用法:
#   ./build.sh <engine> [--version <ver>] [--build-only] [--skip-verify]
#   ./build.sh <engine> --with-security --base-tag <tag> [--build-only]
#   ./build.sh all [--build-only] [--skip-verify]
#
# 省略 --version 时自动检测各引擎最新稳定版（openclaw→npm, nanobot→PyPI）
#
# 示例:
#   ./build.sh all                                    # 所有引擎最新版，构建并推送
#   ./build.sh all --build-only                       # 所有引擎最新版，仅构建
#   ./build.sh openclaw                               # 自动检测最新 OpenClaw
#   ./build.sh nanobot --version 0.1.4
#   ./build.sh hermes                                 # 使用 Hermes 官方 release tag
#   ./build.sh openclaw --with-security --base-tag v2026.3.13
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

# ── 自动检测各引擎最新稳定版 ─────────────────────────
detect_latest_version() {
  local engine="$1"
  case "${engine}" in
    openclaw)
      npm view openclaw versions --json 2>/dev/null | node -e "
        const versions = JSON.parse(require('fs').readFileSync('/dev/stdin', 'utf8'));
        const stable = versions.filter(v => /^\d{4}\.\d{1,2}\.\d{1,2}$/.test(v));
        if (stable.length > 0) console.log(stable[stable.length - 1]);
      "
      ;;
    nanobot)
      curl -sS https://pypi.org/pypi/nanobot-ai/json 2>/dev/null | python3 -c "
import json, sys, re
data = json.load(sys.stdin)
versions = list(data['releases'].keys())
stable = [v for v in versions if re.match(r'^\d+\.\d+\.\d+$', v)]
stable.sort(key=lambda v: list(map(int, v.split('.'))))
print(stable[-1] if stable else '')"
      ;;
    hermes)
      python3 - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("https://api.github.com/repos/NousResearch/hermes-agent/releases/latest", timeout=20) as resp:
    payload = json.load(resp)

print(payload.get("tag_name", ""))
PY
      ;;
  esac
}

ENGINE="$1"; shift || true
if [ -z "${ENGINE}" ]; then
  log_error "用法: ./build.sh <engine> [--version <ver>] [--build-only] [--skip-verify]"
  log_info "可用引擎: openclaw, nanobot, hermes, all"
  exit 1
fi

# ── all 模式: 依次构建所有引擎 ────────────────────────
if [ "${ENGINE}" = "all" ]; then
  FAILED=0
  for e in openclaw nanobot hermes; do
    echo ""
    log_info "==============================="
    log_info "  构建 ${e}"
    log_info "==============================="
    "$0" "${e}" "$@" || { log_error "${e} 构建失败"; FAILED=1; }
  done
  echo ""
  if [ "${FAILED}" = 1 ]; then
    log_error "部分引擎构建失败"
    exit 1
  fi
  log_success "所有引擎构建完成"
  exit 0
fi

ENGINE_DIR="${SCRIPT_DIR}/${ENGINE}-image"
if [ ! -d "${ENGINE_DIR}" ]; then
  log_error "引擎目录不存在: ${ENGINE_DIR}"
  exit 1
fi

check_docker
parse_common_args "$@"
load_mirrors

REGISTRY="$(registry_for "${ENGINE}")"

# --- 版本号归一化：统一去掉用户输入的 v 前缀，tag 统一加 v ---
VERSION="${VERSION#v}"

# --- 安全层模式 ---
if [ "${WITH_SECURITY}" = true ]; then
  CONTEXT_DIR="${SCRIPT_DIR}/../"
  BASE_TAG="${BASE_TAG#v}"
  IMAGE_TAG="v${BASE_TAG}-sec"

  print_build_summary "${ENGINE} (security)" "${BASE_TAG}" "${REGISTRY}" "linux/amd64" "security"

  docker_build "${CONTEXT_DIR}" "${REGISTRY}:${IMAGE_TAG}" \
    -f "${ENGINE_DIR}/Dockerfile.security" \
    --build-arg BASE_TAG="v${BASE_TAG}" \
    --build-arg BASE_REGISTRY="${REGISTRY}"
else
  # --- Base 模式 ---
  if [ -z "${VERSION}" ]; then
    log_info "未指定版本，自动检测 ${ENGINE} 最新稳定版..."
    DETECTED=$(detect_latest_version "${ENGINE}")
    if [ -z "${DETECTED}" ]; then
      log_error "无法自动检测 ${ENGINE} 最新版本，请手动指定 --version"
      exit 1
    fi
    VERSION="${DETECTED#v}"
    log_success "检测到最新版本: ${DETECTED}"
  fi

  if [ "${ENGINE}" = "openclaw" ]; then
    log_info "验证 openclaw@${VERSION} 在 npm 上是否存在..."
    NPM_INFO=$(npm view "openclaw@${VERSION}" version 2>/dev/null || true)
    if [ -z "${NPM_INFO}" ]; then
      log_error "openclaw@${VERSION} 在 npm 上不存在"
      echo "可用的最新版本:"
      npm view openclaw versions --json 2>/dev/null | tail -10
      exit 1
    fi
    log_success "openclaw@${VERSION} 存在"
  fi

  if [ -d "${SCRIPT_DIR}/../nodeskclaw-tunnel-bridge" ] && [ "${ENGINE}" = "nanobot" ]; then
    cp -r "${SCRIPT_DIR}/../nodeskclaw-tunnel-bridge" "${ENGINE_DIR}/nodeskclaw-tunnel-bridge"
    trap "rm -rf '${ENGINE_DIR}/nodeskclaw-tunnel-bridge'" EXIT
  fi

  IMAGE_TAG="v${VERSION}"

  BUILD_ARG_VERSION="${VERSION}"
  if [ "${ENGINE}" = "hermes" ]; then
    BUILD_ARG_VERSION="v${VERSION}"
  fi

  print_build_summary "${ENGINE}" "${VERSION}" "${REGISTRY}" "linux/amd64" "base"

  ENGINE_UPPER="$(echo "${ENGINE}" | tr '[:lower:]' '[:upper:]')"

  if [ "${ENGINE}" = "hermes" ]; then
    HERMES_CONTEXT_DIR="${SCRIPT_DIR}/.."
    docker_build "${HERMES_CONTEXT_DIR}" "${REGISTRY}:${IMAGE_TAG}" \
      -f "${ENGINE_DIR}/Dockerfile" \
      --build-arg "${ENGINE_UPPER}_VERSION=${BUILD_ARG_VERSION}" \
      --build-arg IMAGE_VERSION="${IMAGE_TAG}"
  else
    docker_build "${ENGINE_DIR}" "${REGISTRY}:${IMAGE_TAG}" \
      --build-arg "${ENGINE_UPPER}_VERSION=${BUILD_ARG_VERSION}" \
      --build-arg IMAGE_VERSION="${IMAGE_TAG}"
  fi
fi

# --- 验证（可选）---
if [ "${SKIP_VERIFY}" = false ] && [ "${WITH_SECURITY}" = false ]; then
  log_info "验证镜像（Apple Silicon 上较慢，可用 --skip-verify 跳过）..."
  case "${ENGINE}" in
    openclaw)
      echo "  Node.js: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" node --version)"
      echo "  OpenClaw: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" openclaw --version 2>/dev/null || echo '(需启动后验证)')"
      echo "  版本标记: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" cat /root/.openclaw-version)"
      ;;
    nanobot)
      echo "  Python: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" python --version)"
      echo "  Nanobot: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" pip show nanobot-ai 2>/dev/null | grep Version || echo '(需启动后验证)')"
      ;;
    hermes)
      echo "  Python: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" python --version)"
      echo "  Hermes: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" hermes --help >/dev/null 2>&1 && echo 'hermes cli ok' || echo '(需启动后验证)')"
      echo "  Bridge: $(docker run --rm --platform linux/amd64 "${REGISTRY}:${IMAGE_TAG}" hermes-nodeskclaw-bridge --help >/dev/null 2>&1 && echo 'bridge cli ok' || echo '(需启动后验证)')"
      ;;
  esac
fi

# --- 推送 ---
log_success "构建完成"

if [ "${BUILD_ONLY}" = true ]; then
  log_info "仅构建模式，跳过推送"
  echo "如需推送，运行: docker push ${REGISTRY}:${IMAGE_TAG}"
  exit 0
fi

docker_push "${REGISTRY}:${IMAGE_TAG}"
print_done "${REGISTRY}:${IMAGE_TAG}"
