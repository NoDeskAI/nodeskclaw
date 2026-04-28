"""Unified Channel Schema Registry — canonical channel definitions with per-runtime field mapping."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldDef:
    key: str
    label: str
    type: str  # "string" | "password" | "boolean" | "select" | "string_list" | "number"
    required: bool = False
    placeholder: str = ""
    default: str | bool | int | None = None
    options: tuple[dict, ...] = ()
    runtime_key: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ChannelDefinition:
    label: str
    supported_runtimes: tuple[str, ...]
    fields: tuple[FieldDef, ...]
    order: int = 999
    adapter_runtimes: tuple[str, ...] = ()


UNIFIED_CHANNEL_REGISTRY: dict[str, ChannelDefinition] = {

    # ── Feishu / 飞书 ────────────────────────────────────────
    "feishu": ChannelDefinition(
        label="Feishu / 飞书",
        supported_runtimes=("openclaw", "nanobot", "hermes"),
        order=35,
        fields=(
            FieldDef(
                key="appId", label="App ID", type="string", required=True,
                placeholder="cli_xxxx",
                runtime_key={"openclaw": "appId", "nanobot": "appId", "hermes": "extra.app_id"},
            ),
            FieldDef(
                key="appSecret", label="App Secret", type="password", required=True,
                placeholder="飞书应用的 App Secret",
                runtime_key={"openclaw": "appSecret", "nanobot": "appSecret", "hermes": "extra.app_secret"},
            ),
            FieldDef(
                key="domain", label="Domain（域名）", type="select", required=False,
                default="feishu",
                options=(
                    {"value": "feishu", "label": "feishu（飞书国内）"},
                    {"value": "lark", "label": "lark（海外 Lark）"},
                ),
                runtime_key={"openclaw": "domain", "hermes": "extra.domain"},
            ),
            FieldDef(
                key="connectionMode", label="Connection Mode（连接方式）", type="select",
                required=False, default="websocket",
                options=(
                    {"value": "websocket", "label": "WebSocket（长连接，推荐）"},
                    {"value": "webhook", "label": "Webhook（需公网回调）"},
                ),
                runtime_key={"openclaw": "connectionMode", "hermes": "extra.connection_mode"},
            ),
            FieldDef(
                key="allowFrom", label="Allow From（允许列表）", type="string_list",
                required=False,
                runtime_key={"openclaw": "allowFrom", "nanobot": "allowFrom"},
            ),
            FieldDef(
                key="dmPolicy", label="DM Policy（私聊策略）", type="select",
                required=False, default="open",
                options=(
                    {"value": "open", "label": "open（所有人可用）"},
                    {"value": "pairing", "label": "pairing（需配对）"},
                    {"value": "allowlist", "label": "allowlist（白名单）"},
                ),
                runtime_key={"openclaw": "dmPolicy"},
            ),
            FieldDef(
                key="groupPolicy", label="Group Policy（群聊策略）", type="select",
                required=False, default="open",
                options=(
                    {"value": "open", "label": "open（开放）"},
                    {"value": "mention", "label": "mention（需@提及）"},
                    {"value": "allowlist", "label": "allowlist（白名单）"},
                    {"value": "disabled", "label": "disabled（禁用群聊）"},
                ),
                runtime_key={
                    "openclaw": "groupPolicy",
                    "nanobot": "groupPolicy",
                    "hermes": "extra.default_group_policy",
                },
            ),
            FieldDef(
                key="requireMention", label="Require Mention（需@提及）", type="boolean",
                required=False, default=False,
                runtime_key={"openclaw": "requireMention"},
            ),
            FieldDef(
                key="topicSessionMode", label="Topic Session Mode（话题模式）",
                type="select", required=False, default="disabled",
                options=(
                    {"value": "disabled", "label": "disabled"},
                    {"value": "enabled", "label": "enabled"},
                ),
                runtime_key={"openclaw": "topicSessionMode"},
            ),
            FieldDef(
                key="encryptKey", label="Encrypt Key（事件加密密钥）", type="password",
                required=False, placeholder="可选，Webhook 模式下使用",
                runtime_key={"openclaw": "encryptKey", "nanobot": "encryptKey"},
            ),
            FieldDef(
                key="verificationToken", label="Verification Token（验证令牌）",
                type="password", required=False, placeholder="可选，Webhook 模式下使用",
                runtime_key={"openclaw": "verificationToken", "nanobot": "verificationToken"},
            ),
            FieldDef(
                key="reactEmoji", label="React Emoji（反应表情）", type="string",
                required=False, default="THUMBSUP", placeholder="THUMBSUP",
                runtime_key={"nanobot": "reactEmoji"},
            ),
            FieldDef(
                key="replyToMessage", label="Reply To Message（引用回复）", type="boolean",
                required=False, default=False,
                runtime_key={"nanobot": "replyToMessage"},
            ),
        ),
    ),

    # ── Telegram ─────────────────────────────────────────────
    "telegram": ChannelDefinition(
        label="Telegram",
        supported_runtimes=("openclaw", "nanobot", "hermes"),
        order=45,
        fields=(
            FieldDef(
                key="botToken", label="Bot Token", type="password", required=True,
                placeholder="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
                runtime_key={"openclaw": "botToken", "nanobot": "token", "hermes": "token"},
            ),
            FieldDef(
                key="allowFrom", label="Allow From（允许列表）", type="string_list",
                required=False,
                runtime_key={"nanobot": "allowFrom"},
            ),
            FieldDef(
                key="groupPolicy", label="Group Policy（群聊策略）", type="select",
                required=False, default="mention",
                options=(
                    {"value": "open", "label": "open（开放）"},
                    {"value": "mention", "label": "mention（需@提及）"},
                ),
                runtime_key={"nanobot": "groupPolicy", "hermes": "extra.require_mention"},
            ),
            FieldDef(
                key="proxy", label="Proxy（代理地址）", type="string",
                required=False, placeholder="socks5://127.0.0.1:1080",
                runtime_key={"nanobot": "proxy"},
            ),
            FieldDef(
                key="replyToMessage", label="Reply To Message（引用回复）", type="boolean",
                required=False, default=False,
                runtime_key={"nanobot": "replyToMessage"},
            ),
        ),
    ),

    # ── Discord ──────────────────────────────────────────────
    "discord": ChannelDefinition(
        label="Discord",
        supported_runtimes=("openclaw", "nanobot", "hermes"),
        order=50,
        fields=(
            FieldDef(
                key="token", label="Bot Token", type="password", required=True,
                placeholder="Discord Bot Token",
                runtime_key={"openclaw": "token", "nanobot": "token", "hermes": "token"},
            ),
            FieldDef(
                key="allowFrom", label="Allow From（允许列表）", type="string_list",
                required=False,
                runtime_key={"nanobot": "allowFrom"},
            ),
            FieldDef(
                key="groupPolicy", label="Group Policy（群聊策略）", type="select",
                required=False, default="mention",
                options=(
                    {"value": "mention", "label": "mention（需@提及）"},
                    {"value": "open", "label": "open（开放）"},
                ),
                runtime_key={"nanobot": "groupPolicy", "hermes": "extra.require_mention"},
            ),
        ),
    ),

    # ── Slack ────────────────────────────────────────────────
    "slack": ChannelDefinition(
        label="Slack",
        supported_runtimes=("openclaw", "nanobot"),
        order=40,
        fields=(
            FieldDef(
                key="botToken", label="Bot Token", type="password", required=True,
                placeholder="xoxb-xxxx",
                runtime_key={"openclaw": "botToken", "nanobot": "botToken"},
            ),
            FieldDef(
                key="appToken", label="App Token", type="password", required=True,
                placeholder="xapp-xxxx",
                runtime_key={"openclaw": "appToken", "nanobot": "appToken"},
            ),
            FieldDef(
                key="allowFrom", label="Allow From（允许列表）", type="string_list",
                required=False,
                runtime_key={"nanobot": "allowFrom"},
            ),
            FieldDef(
                key="groupPolicy", label="Group Policy（群聊策略）", type="select",
                required=False, default="mention",
                options=(
                    {"value": "mention", "label": "mention（需@提及）"},
                    {"value": "open", "label": "open（开放）"},
                    {"value": "allowlist", "label": "allowlist（白名单）"},
                ),
                runtime_key={"nanobot": "groupPolicy"},
            ),
            FieldDef(
                key="replyInThread", label="Reply In Thread（线程内回复）", type="boolean",
                required=False, default=True,
                runtime_key={"nanobot": "replyInThread"},
            ),
            FieldDef(
                key="reactEmoji", label="React Emoji（反应表情）", type="string",
                required=False, default="eyes",
                runtime_key={"nanobot": "reactEmoji"},
            ),
        ),
    ),

    # ── DingTalk / 钉钉 ─────────────────────────────────────
    "dingtalk": ChannelDefinition(
        label="DingTalk / 钉钉",
        supported_runtimes=("openclaw", "nanobot", "hermes"),
        order=36,
        fields=(
            FieldDef(
                key="clientId", label="Client ID（应用凭证）", type="string", required=True,
                placeholder="dingxxxxxxx",
                runtime_key={"openclaw": "clientId", "nanobot": "clientId", "hermes": "extra.client_id"},
            ),
            FieldDef(
                key="clientSecret", label="Client Secret（应用密钥）", type="password",
                required=True, placeholder="钉钉应用的 Client Secret",
                runtime_key={"openclaw": "clientSecret", "nanobot": "clientSecret", "hermes": "extra.client_secret"},
            ),
            FieldDef(
                key="agentId", label="Agent ID（机器人 ID）", type="string", required=False,
                placeholder="可选，用于主动发消息",
                runtime_key={"openclaw": "agentId"},
            ),
            FieldDef(
                key="robotCode", label="Robot Code（机器人编码）", type="string",
                required=False, placeholder="通常与 Client ID 相同",
                runtime_key={"openclaw": "robotCode"},
            ),
            FieldDef(
                key="corpId", label="Corp ID（企业 ID）", type="string", required=False,
                placeholder="可选",
                runtime_key={"openclaw": "corpId"},
            ),
            FieldDef(
                key="allowFrom", label="Allow From（允许列表）", type="string_list",
                required=False,
                runtime_key={"nanobot": "allowFrom"},
            ),
            FieldDef(
                key="dmPolicy", label="DM Policy（私聊策略）", type="select",
                required=False, default="open",
                options=(
                    {"value": "open", "label": "open（所有人可用）"},
                    {"value": "allowFrom", "label": "allowFrom（白名单）"},
                ),
                runtime_key={"openclaw": "dmPolicy"},
            ),
            FieldDef(
                key="groupPolicy", label="Group Policy（群聊策略）", type="select",
                required=False, default="mention",
                options=(
                    {"value": "mention", "label": "mention（需@提及）"},
                    {"value": "open", "label": "open（开放）"},
                    {"value": "allowlist", "label": "allowlist（白名单）"},
                    {"value": "disabled", "label": "disabled（禁用群聊）"},
                ),
                runtime_key={"openclaw": "groupPolicy"},
            ),
            FieldDef(
                key="messageType", label="Message Type（消息格式）", type="select",
                required=False, default="markdown",
                options=(
                    {"value": "markdown", "label": "Markdown"},
                    {"value": "card", "label": "Card（交互卡片）"},
                ),
                runtime_key={"openclaw": "messageType"},
            ),
        ),
    ),
}


def get_channel_schema(
    channel_id: str,
    runtime_id: str | None = None,
) -> list[dict] | None:
    """Return schema fields for a channel, optionally filtered by runtime.

    If runtime_id is given, only fields that apply to that runtime are returned
    and each field dict includes ``applicable: bool`` for UI rendering.
    """
    defn = UNIFIED_CHANNEL_REGISTRY.get(channel_id)
    if defn is None:
        return None

    result: list[dict] = []
    for f in defn.fields:
        entry: dict = {
            "key": f.key,
            "label": f.label,
            "type": f.type,
            "required": f.required,
        }
        if f.placeholder:
            entry["placeholder"] = f.placeholder
        if f.default is not None:
            entry["default"] = f.default
        if f.options:
            entry["options"] = list(f.options)
        if f.runtime_key:
            entry["runtime_key"] = f.runtime_key

        if runtime_id:
            entry["applicable"] = runtime_id in f.runtime_key
        result.append(entry)
    return result


def get_legacy_channel_schemas() -> dict[str, list[dict]]:
    """Generate a backward-compatible CHANNEL_SCHEMAS dict from the unified registry.

    Used by API endpoints that still expect the old format.
    """
    result: dict[str, list[dict]] = {}
    for channel_id, defn in UNIFIED_CHANNEL_REGISTRY.items():
        fields = []
        for f in defn.fields:
            if "openclaw" not in f.runtime_key:
                continue
            entry: dict = {
                "key": f.key,
                "label": f.label,
                "type": f.type,
                "required": f.required,
            }
            if f.placeholder:
                entry["placeholder"] = f.placeholder
            if f.default is not None:
                entry["default"] = f.default
            if f.options:
                entry["options"] = list(f.options)
            fields.append(entry)
        if fields:
            result[channel_id] = fields
    return result
