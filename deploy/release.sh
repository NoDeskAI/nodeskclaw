#!/usr/bin/env bash
# ============================================================
# NoDeskClaw 发布工作流脚本
#
# 用法:
#   ./deploy/release.sh <subcommand> <version> [options]
#
# 子命令:
#   staging    构建 + 推送 + 部署到 staging namespace（含 LLM proxy）
#   release    打 git tag + 创建 GitHub Pre-release
#   promote    将 staging 验证过的镜像部署到 production namespace
#   full       staging -> release -> promote 全流程（每步需确认）
#
# 选项:
#   --context CTX       K8s 上下文（staging/promote 必填）
#   --staging-ns NS     staging namespace（默认 nodeskclaw-staging）
#   --prod-ns NS        production namespace（默认 nodeskclaw-system）
#   --skip-proxy        跳过 LLM proxy 部署
#   --no-cache          docker build 不使用缓存
#
# 前置条件:
#   - gh CLI 已安装并认证（release 阶段需要）
#   - docker login 已完成
#   - deploy/.env.local 已配置 REGISTRY
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

STAGING_NS="nodeskclaw-staging"
PROD_NS="nodeskclaw-system"
KUBE_CONTEXT=""
SKIP_PROXY=false
NO_CACHE=""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[Release]${NC} $*"; }
ok()   { echo -e "${GREEN}[  OK  ]${NC} $*"; }
warn() { echo -e "${YELLOW}[ WARN ]${NC} $*"; }
err()  { echo -e "${RED}[ERROR ]${NC} $*" >&2; }

usage() {
  echo "用法: $0 <staging|release|promote|full> <version> [options]"
  echo ""
  echo "选项:"
  echo "  --context CTX       K8s 上下文（staging/promote 必填）"
  echo "  --staging-ns NS     staging namespace（默认 nodeskclaw-staging）"
  echo "  --prod-ns NS        production namespace（默认 nodeskclaw-system）"
  echo "  --skip-proxy        跳过 LLM proxy 构建/部署"
  echo "  --no-cache          docker build 不使用缓存"
  exit 1
}

[[ $# -lt 2 ]] && usage

SUBCMD="$1"; shift
VERSION="$1"; shift

while [[ $# -gt 0 ]]; do
  case "$1" in
    --context)      KUBE_CONTEXT="$2"; shift ;;
    --staging-ns)   STAGING_NS="$2"; shift ;;
    --prod-ns)      PROD_NS="$2"; shift ;;
    --skip-proxy)   SKIP_PROXY=true ;;
    --no-cache)     NO_CACHE="--no-cache" ;;
    *)              err "未知参数: $1"; usage ;;
  esac
  shift
done

# ── 工具函数 ─────────────────────────────────────────────

confirm() {
  local msg="$1"
  echo ""
  echo -e "${YELLOW}$msg${NC}"
  read -r -p "继续? [y/N] " answer
  [[ "$answer" =~ ^[Yy]$ ]] || { log "已取消"; exit 0; }
}

require_context() {
  if [[ -z "$KUBE_CONTEXT" ]]; then
    err "$SUBCMD 子命令需要 --context 参数"
    usage
  fi
}

require_gh() {
  if ! command -v gh &>/dev/null; then
    err "gh CLI 未安装。请运行: brew install gh"
    exit 1
  fi
  if ! gh auth status &>/dev/null; then
    err "gh CLI 未认证。请运行: gh auth login"
    exit 1
  fi
}

generate_changelog() {
  local version="$1"
  local tmpfile; tmpfile="$(mktemp)"
  local last_tag; last_tag="$(git -C "$PROJECT_ROOT" describe --tags --abbrev=0 2>/dev/null || echo '')"

  local range="HEAD"
  if [[ -n "$last_tag" ]]; then
    range="${last_tag}..HEAD"
  fi

  local feats="" fixes="" refactors="" others=""

  while IFS= read -r line; do
    if [[ "$line" =~ ^feat ]]; then
      feats+="- ${line}"$'\n'
    elif [[ "$line" =~ ^fix ]]; then
      fixes+="- ${line}"$'\n'
    elif [[ "$line" =~ ^refactor|^perf ]]; then
      refactors+="- ${line}"$'\n'
    elif [[ "$line" =~ ^chore|^docs|^style|^build|^test ]]; then
      others+="- ${line}"$'\n'
    else
      others+="- ${line}"$'\n'
    fi
  done < <(git -C "$PROJECT_ROOT" log "$range" --pretty=format:"%s" --no-merges)

  {
    echo "# ${version}"
    echo ""
    if [[ -n "$feats" ]]; then
      echo "## New Features"
      echo ""
      echo "$feats"
    fi
    if [[ -n "$fixes" ]]; then
      echo "## Bug Fixes"
      echo ""
      echo "$fixes"
    fi
    if [[ -n "$refactors" ]]; then
      echo "## Refactoring & Performance"
      echo ""
      echo "$refactors"
    fi
    if [[ -n "$others" ]]; then
      echo "## Other Changes"
      echo ""
      echo "$others"
    fi
    echo ""
    if [[ -n "$last_tag" ]]; then
      echo "**Full Changelog**: https://github.com/NoDeskAI/nodeskclaw/compare/${last_tag}...${version}"
    fi
  } > "$tmpfile"

  echo "$tmpfile"
}

# ── staging ──────────────────────────────────────────────

do_staging() {
  require_context
  log "=== STAGING: 构建并部署 ${VERSION} 到 ${STAGING_NS} ==="
  echo ""

  local cache_flag=""
  [[ -n "$NO_CACHE" ]] && cache_flag="--no-cache"

  log "1/4 构建 backend + admin + portal..."
  "$SCRIPT_DIR/deploy.sh" all --build-only --tag "$VERSION" $cache_flag

  if [[ "$SKIP_PROXY" != true ]]; then
    log "2/4 构建 LLM proxy..."
    "$PROJECT_ROOT/nodeskclaw-llm-proxy/deploy.sh" --context "$KUBE_CONTEXT" --build-only --tag "$VERSION" $cache_flag
  else
    warn "2/4 跳过 LLM proxy 构建"
  fi

  log "3/4 部署 backend + admin + portal 到 ${STAGING_NS}..."
  "$SCRIPT_DIR/deploy.sh" all --deploy-only --tag "$VERSION" --namespace "$STAGING_NS" --context "$KUBE_CONTEXT"

  if [[ "$SKIP_PROXY" != true ]]; then
    log "4/4 部署 LLM proxy 到 ${STAGING_NS}..."
    "$PROJECT_ROOT/nodeskclaw-llm-proxy/deploy.sh" --deploy-only --tag "$VERSION" --namespace "$STAGING_NS" --context "$KUBE_CONTEXT"
  else
    warn "4/4 跳过 LLM proxy 部署"
  fi

  echo ""
  ok "Staging 部署完成: ${VERSION} -> ${STAGING_NS}"
  log "请在 staging 环境验证功能后，运行:"
  echo "  ./deploy/release.sh release ${VERSION}"
}

# ── release ──────────────────────────────────────────────

do_release() {
  require_gh
  log "=== RELEASE: 创建 GitHub Release ${VERSION} ==="
  echo ""

  log "生成 changelog..."
  local notes_file; notes_file="$(generate_changelog "$VERSION")"
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  cat "$notes_file"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  confirm "即将创建 git tag ${VERSION} 并发布 GitHub Pre-release"

  log "创建 git tag..."
  git -C "$PROJECT_ROOT" tag "$VERSION"
  git -C "$PROJECT_ROOT" push origin "$VERSION"

  log "创建 GitHub Pre-release..."
  gh release create "$VERSION" \
    --repo NoDeskAI/nodeskclaw \
    --prerelease \
    --title "$VERSION" \
    --notes-file "$notes_file"

  rm -f "$notes_file"

  echo ""
  ok "GitHub Pre-release 已创建: ${VERSION}"
  log "验证地址: https://github.com/NoDeskAI/nodeskclaw/releases/tag/${VERSION}"
  log "准备好升级生产环境后，运行:"
  echo "  ./deploy/release.sh promote ${VERSION} --context <ctx>"
}

# ── promote ──────────────────────────────────────────────

do_promote() {
  require_context
  log "=== PROMOTE: 将 ${VERSION} 部署到生产环境 ${PROD_NS} ==="
  echo ""

  confirm "即将将 ${VERSION} 部署到生产环境 ${PROD_NS}（集群: ${KUBE_CONTEXT}）"

  log "1/2 部署 backend + admin + portal 到 ${PROD_NS}..."
  "$SCRIPT_DIR/deploy.sh" all --deploy-only --tag "$VERSION" --namespace "$PROD_NS" --context "$KUBE_CONTEXT"

  if [[ "$SKIP_PROXY" != true ]]; then
    log "2/2 部署 LLM proxy 到 ${PROD_NS}..."
    "$PROJECT_ROOT/nodeskclaw-llm-proxy/deploy.sh" --deploy-only --tag "$VERSION" --namespace "$PROD_NS" --context "$KUBE_CONTEXT"
  else
    warn "2/2 跳过 LLM proxy 部署"
  fi

  log "更新 GitHub Release 为正式版..."
  if command -v gh &>/dev/null && gh auth status &>/dev/null 2>&1; then
    gh release edit "$VERSION" --repo NoDeskAI/nodeskclaw --prerelease=false 2>/dev/null || \
      warn "无法更新 GitHub Release（可能 tag 不存在或未发布），请手动执行: gh release edit ${VERSION} --prerelease=false"
  else
    warn "gh CLI 不可用，请手动执行: gh release edit ${VERSION} --prerelease=false"
  fi

  echo ""
  ok "生产环境部署完成: ${VERSION} -> ${PROD_NS}"
}

# ── full ─────────────────────────────────────────────────

do_full() {
  require_context
  log "=== FULL: 完整发布流程 ${VERSION} ==="
  echo ""

  confirm "即将执行完整发布流程: staging -> release -> promote"

  do_staging
  echo ""
  confirm "Staging 已部署。测试验证完成后继续创建 Release?"
  do_release
  echo ""
  confirm "Release 已创建。继续升级生产环境?"
  do_promote

  echo ""
  ok "完整发布流程完成: ${VERSION}"
}

# ── 分发 ─────────────────────────────────────────────────

case "$SUBCMD" in
  staging) do_staging ;;
  release) do_release ;;
  promote) do_promote ;;
  full)    do_full ;;
  *)       err "未知子命令: $SUBCMD"; usage ;;
esac
