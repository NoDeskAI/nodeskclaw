#!/usr/bin/env bash
set -euo pipefail

export HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
export API_SERVER_ENABLED="${API_SERVER_ENABLED:-true}"
export API_SERVER_HOST="${API_SERVER_HOST:-0.0.0.0}"
export API_SERVER_PORT="${API_SERVER_PORT:-8642}"
export HERMES_BASE_URL="${HERMES_BASE_URL:-http://127.0.0.1:${API_SERVER_PORT}}"
export HERMES_DEFAULT_MEMORY_ENABLED="${HERMES_DEFAULT_MEMORY_ENABLED:-true}"
export HERMES_DEFAULT_USER_PROFILE_ENABLED="${HERMES_DEFAULT_USER_PROFILE_ENABLED:-true}"
export HERMES_WORKSPACE_ROOT="${HERMES_WORKSPACE_ROOT:-${HERMES_HOME}/workspace}"
export NODESKCLAW_WORKSPACE_ROOT="${NODESKCLAW_WORKSPACE_ROOT:-/root/.openclaw/workspace}"
export TERMINAL_CWD="${TERMINAL_CWD:-${NODESKCLAW_WORKSPACE_ROOT}}"
export DESKCLAW_API_URL="${DESKCLAW_API_URL:-${NODESKCLAW_API_URL:-}}"
export DESKCLAW_TOKEN="${DESKCLAW_TOKEN:-${NODESKCLAW_TOKEN:-}}"
export DESKCLAW_INSTANCE_ID="${DESKCLAW_INSTANCE_ID:-${NODESKCLAW_INSTANCE_ID:-}}"
export DESKCLAW_WORKSPACE_ID="${DESKCLAW_WORKSPACE_ID:-${NODESKCLAW_WORKSPACE_ID:-}}"
export DESKCLAW_WORKSPACE_ROOT="${DESKCLAW_WORKSPACE_ROOT:-${NODESKCLAW_WORKSPACE_ROOT}}"

mkdir -p "${HERMES_HOME}/logs" \
         "${HERMES_HOME}/skills" \
         "${HERMES_HOME}/scripts" \
         "${HERMES_HOME}/cron" \
         "${HERMES_HOME}/sessions" \
         "${HERMES_HOME}/memories" \
         "${HERMES_WORKSPACE_ROOT}" \
         "${HERMES_WORKSPACE_ROOT}/uploads" \
         "/root/.openclaw"

ln -sfn "${HERMES_WORKSPACE_ROOT}" "${NODESKCLAW_WORKSPACE_ROOT}"

RUNTIME_ENV_SH="/tmp/hermes-runtime-env.sh"

python - <<'PY'
from pathlib import Path
import os
import shlex

import yaml

config_path = Path(os.environ["HERMES_HOME"]) / "config.yaml"
runtime_env_path = Path("/tmp/hermes-runtime-env.sh")

if config_path.exists():
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[entrypoint] config.yaml 解析失败，跳过 memory 默认项注入: {exc}")
        raw = None
else:
    raw = {}

if raw is None:
    raw = {}
if not isinstance(raw, dict):
    print("[entrypoint] config.yaml 根节点不是对象，跳过 memory 默认项注入")
else:
    memory_cfg = raw.get("memory")
    if not isinstance(memory_cfg, dict):
        memory_cfg = {}
    changed = False

    def _env_bool(name: str, default: bool) -> bool:
        value = os.environ.get(name, "")
        if not value:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    if "memory_enabled" not in memory_cfg:
        memory_cfg["memory_enabled"] = _env_bool("HERMES_DEFAULT_MEMORY_ENABLED", True)
        changed = True
    if "user_profile_enabled" not in memory_cfg:
        memory_cfg["user_profile_enabled"] = _env_bool("HERMES_DEFAULT_USER_PROFILE_ENABLED", True)
        changed = True

    if changed or "memory" not in raw:
        raw["memory"] = memory_cfg
        config_path.write_text(
            yaml.safe_dump(raw, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        print(
            "[entrypoint] 已确保 Hermes memory 默认开启 "
            f"(memory_enabled={memory_cfg.get('memory_enabled')}, "
            f"user_profile_enabled={memory_cfg.get('user_profile_enabled')})"
        )

runtime_exports: dict[str, str] = {}
platforms = raw.get("platforms")
if not isinstance(platforms, dict):
    platforms = {}

feishu_cfg = platforms.get("feishu")
if isinstance(feishu_cfg, dict) and feishu_cfg.get("enabled"):
    extra = feishu_cfg.get("extra")
    if not isinstance(extra, dict):
        extra = {}

    def _set_if_missing(name: str, value: object | None) -> None:
        if os.environ.get(name):
            return
        if value is None:
            return
        rendered = str(value).strip()
        if rendered:
            runtime_exports[name] = rendered

    def _set_bool_if_missing(name: str, value: bool) -> None:
        if os.environ.get(name):
            return
        runtime_exports[name] = "true" if value else "false"

    _set_if_missing("FEISHU_APP_ID", extra.get("app_id"))
    _set_if_missing("FEISHU_APP_SECRET", extra.get("app_secret"))
    _set_if_missing("FEISHU_DOMAIN", extra.get("domain"))
    _set_if_missing("FEISHU_CONNECTION_MODE", extra.get("connection_mode"))
    _set_if_missing("FEISHU_ENCRYPT_KEY", feishu_cfg.get("encryptKey"))
    _set_if_missing("FEISHU_VERIFICATION_TOKEN", feishu_cfg.get("verificationToken"))

    dm_policy = str(feishu_cfg.get("dmPolicy", "") or "").strip().lower()
    allow_from = feishu_cfg.get("allowFrom")
    if isinstance(allow_from, list):
        allow_from_list = [str(item).strip() for item in allow_from if str(item).strip()]
    elif isinstance(allow_from, str):
        allow_from_list = [item.strip() for item in allow_from.split(",") if item.strip()]
    else:
        allow_from_list = []

    if dm_policy == "open":
        _set_bool_if_missing("FEISHU_ALLOW_ALL_USERS", True)
    elif dm_policy == "allowlist":
        _set_bool_if_missing("FEISHU_ALLOW_ALL_USERS", False)
        _set_if_missing("FEISHU_ALLOWED_USERS", ",".join(allow_from_list))
    elif dm_policy == "pairing":
        _set_bool_if_missing("FEISHU_ALLOW_ALL_USERS", False)

    group_policy = str(
        extra.get("default_group_policy")
        or feishu_cfg.get("groupPolicy")
        or ""
    ).strip().lower()
    if group_policy == "mention":
        group_policy = "open"
    _set_if_missing("FEISHU_GROUP_POLICY", group_policy)

lines = ["#!/usr/bin/env sh", "set -eu"]
for key, value in sorted(runtime_exports.items()):
    lines.append(f"export {key}={shlex.quote(value)}")
runtime_env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
if runtime_exports:
    print("[entrypoint] 已从 config.yaml 注入 Hermes runtime 环境变量: " + ", ".join(sorted(runtime_exports)))
PY

# shellcheck disable=SC1090
. "${RUNTIME_ENV_SH}"

if [ -z "${API_SERVER_KEY:-}" ]; then
  API_SERVER_KEY="$(python - <<'PY'
import secrets
print(secrets.token_hex(24))
PY
)"
  export API_SERVER_KEY
  echo "[entrypoint] API_SERVER_KEY 未指定，已自动生成容器内随机密钥"
fi

echo "[entrypoint] Hermes image version: $(cat /opt/hermes/.hermes-version)"
echo "[entrypoint] Hermes API server: ${API_SERVER_HOST}:${API_SERVER_PORT}"
echo "[entrypoint] Hermes base URL: ${HERMES_BASE_URL}"
echo "[entrypoint] Hermes workspace root: ${NODESKCLAW_WORKSPACE_ROOT}"

if [ "$#" -gt 0 ] && [[ "${1}" != -* ]]; then
  exec "$@"
fi

hermes gateway &
GATEWAY_PID=$!

cleanup() {
  if kill -0 "${GATEWAY_PID}" 2>/dev/null; then
    kill "${GATEWAY_PID}" 2>/dev/null || true
    wait "${GATEWAY_PID}" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

exec hermes-nodeskclaw-bridge "$@"
