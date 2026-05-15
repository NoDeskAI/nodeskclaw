#!/usr/bin/env bash
# NoDeskClaw release CLI: build version artifacts and manage GitHub Releases.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/build.sh"

usage() {
  local exit_code="${1:-1}"
  cat <<EOF
用法: $0 <command> <version> [options]

命令:
  create <version>     构建并推送版本镜像，创建 git tag 和 GitHub Pre-release
  finalize <version>   将 GitHub Release 标记为正式版

选项:
  --ee              EE 模式（包含 admin，启用 ee/ 代码注入）
  --skip-proxy      create 时跳过 proxy 镜像
  --skip-genehub    create 时跳过 genehub 镜像
  --mirrors NAME    使用镜像源预设（如 cn），加速构建依赖下载
  --no-cache        create 时不使用 Docker 缓存
EOF
  exit "$exit_code"
}

generate_changelog() {
  local version="$1"
  local tmpfile; tmpfile="$(mktemp)"
  local last_tag; last_tag="$(git -C "$PROJECT_ROOT" describe --tags --abbrev=0 --exclude="$version" 2>/dev/null || echo '')"

  local range="HEAD"
  [[ -n "$last_tag" ]] && range="${last_tag}..HEAD"

  local feats="" fixes="" refactors="" others=""

  while IFS= read -r line || [[ -n "$line" ]]; do
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
    [[ -n "$feats" ]] && { echo "## New Features"; echo ""; echo "$feats"; }
    [[ -n "$fixes" ]] && { echo "## Bug Fixes"; echo ""; echo "$fixes"; }
    [[ -n "$refactors" ]] && { echo "## Refactoring & Performance"; echo ""; echo "$refactors"; }
    [[ -n "$others" ]] && { echo "## Other Changes"; echo ""; echo "$others"; }
    echo ""
    [[ -n "$last_tag" ]] && echo "**Full Changelog**: https://github.com/NoDeskAI/nodeskclaw/compare/${last_tag}...${version}"
  } > "$tmpfile"

  echo "$tmpfile"
}

cmd_create() {
  require_gh
  ensure_edition
  load_mirrors "$MIRRORS"
  TAG="$VERSION"

  local ce_registry="${PUBLIC_REGISTRY:-$REGISTRY}"
  local has_admin=false
  [[ "$EE_MODE" == true ]] && has_admin=true

  log "=== RELEASE CREATE: 构建镜像 + 创建 GitHub Release ${VERSION} ==="
  log "镜像仓库: ${ce_registry}"
  [[ "$has_admin" == true ]] && log "Admin 仓库: ${REGISTRY}"
  echo ""

  local targets=(backend portal)
  [[ "$SKIP_PROXY" != true ]] && targets+=(proxy)
  [[ "$SKIP_GENEHUB" != true ]] && targets+=(genehub)

  log "生成 changelog..."
  local notes_file; notes_file="$(generate_changelog "$VERSION")"
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  cat "$notes_file"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  local tag_local=false tag_remote=false release_exists=false overwrite_tag=false overwrite_release=false
  git -C "$PROJECT_ROOT" rev-parse "refs/tags/$VERSION" &>/dev/null && tag_local=true
  git -C "$PROJECT_ROOT" ls-remote --tags origin "refs/tags/$VERSION" 2>/dev/null | grep -q . && tag_remote=true
  gh release view "$VERSION" --repo NoDeskAI/nodeskclaw &>/dev/null && release_exists=true

  if [[ "$tag_local" == true || "$tag_remote" == true || "$release_exists" == true ]]; then
    echo ""
    warn "检测到已有 release 产物:"
    if [[ "$tag_local" == true || "$tag_remote" == true ]]; then
      local where=""
      [[ "$tag_local" == true ]] && where+="本地"
      [[ "$tag_local" == true && "$tag_remote" == true ]] && where+=" + "
      [[ "$tag_remote" == true ]] && where+="远程"
      warn "  - git tag ${VERSION}（${where}）"
      overwrite_tag=true
    fi
    [[ "$release_exists" == true ]] && warn "  - GitHub Release $VERSION" && overwrite_release=true
    echo ""
    read -rp "覆盖以上内容并继续 release? [y/N] " ans
    [[ ! "$ans" =~ ^[Yy]$ ]] && err "已取消" && exit 1
  fi

  local confirm_msg="即将构建镜像（${targets[*]} -> ${ce_registry}"
  [[ "$has_admin" == true ]] && confirm_msg+="，admin -> ${REGISTRY}"
  confirm_msg+="）、创建 git tag ${VERSION} 并发布 GitHub Pre-release"
  confirm "$confirm_msg"

  [[ "$has_admin" == true ]] && targets+=(admin)

  log "构建并推送镜像（标签: ${TAG}）..."
  for target in "${targets[@]}"; do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if ! build_and_push "$target"; then
      err "[$(ctag "$target")] 镜像构建失败，中止 release"
      exit 1
    fi
  done

  echo ""
  log "创建 git tag..."
  if [[ "$overwrite_tag" == true ]]; then
    [[ "$tag_local" == true ]] && git -C "$PROJECT_ROOT" tag -d "$VERSION"
    git -C "$PROJECT_ROOT" tag "$VERSION"
    git -C "$PROJECT_ROOT" push origin "$VERSION" --force
  else
    git -C "$PROJECT_ROOT" tag "$VERSION"
    git -C "$PROJECT_ROOT" push origin "$VERSION"
  fi

  log "创建 GitHub Pre-release..."
  [[ "$overwrite_release" == true ]] && gh release delete "$VERSION" --repo NoDeskAI/nodeskclaw --yes

  gh release create "$VERSION" \
    --repo NoDeskAI/nodeskclaw \
    --prerelease \
    --title "$VERSION" \
    --notes-file "$notes_file"

  rm -f "$notes_file"

  echo ""
  ok "GitHub Pre-release 已创建: ${VERSION}"
  log "镜像: ${ce_registry}/*:${TAG}"
  [[ "$has_admin" == true ]] && log "Admin 镜像: ${REGISTRY}/nodeskclaw-admin:${TAG}"
  log "验证地址: https://github.com/NoDeskAI/nodeskclaw/releases/tag/${VERSION}"
}

cmd_finalize() {
  require_gh
  log "=== RELEASE FINALIZE: ${VERSION} ==="
  gh release edit "$VERSION" --repo NoDeskAI/nodeskclaw --prerelease=false
  ok "GitHub Release 已标记为正式版: ${VERSION}"
}

[[ $# -lt 1 ]] && usage 1

COMMAND="$1"; shift
VERSION=""
SKIP_PROXY=false
SKIP_GENEHUB=false
EE_MODE=false
CE_ONLY=true
MIRRORS="${MIRRORS:-}"
NO_CACHE=""

case "$COMMAND" in
  create|finalize)
    if [[ $# -lt 1 || "$1" =~ ^-- ]]; then
      err "$COMMAND 命令需要 version 参数"
      usage 1
    fi
    VERSION="$1"; shift
    ;;
  --help|-h)
    usage 0
    ;;
  *)
    err "未知命令: $COMMAND"
    usage 1
    ;;
esac

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ee)            EE_MODE=true ;;
    --skip-proxy)    SKIP_PROXY=true ;;
    --skip-genehub)  SKIP_GENEHUB=true ;;
    --mirrors)       require_option_value "$1" "${2:-}"; MIRRORS="$2"; shift ;;
    --no-cache)      NO_CACHE="--no-cache" ;;
    --help|-h)       usage 0 ;;
    *)               err "未知参数: $1"; usage 1 ;;
  esac
  shift
done

case "$COMMAND" in
  create)   cmd_create ;;
  finalize) cmd_finalize ;;
esac
