# NoDesk AI Gateway - API 调用指南

> **网关地址**：`http://172.168.20.130:8080`
> **API Key**：`nd-c2dbf13988de84899ce461e812192d447eed5aed35244f85ba73bf65a2afccd6`
> **渠道名称**：`aws`
> **状态**：全部接口已验证通过 ✅ (2026-04-17)

---

## 一、透传接口（Passthrough）

透传模式：请求原样转发到 AWS Bedrock，返回 Anthropic 原生格式。

**接口地址**：`POST /default/passthrough`

### 1. Claude Sonnet 4 ✅

```bash
curl -X POST http://172.168.20.130:8080/default/passthrough \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer nd-c2dbf13988de84899ce461e812192d447eed5aed35244f85ba73bf65a2afccd6" \
  -d '{
    "channel": "aws",
    "channel_url": "https://bedrock-runtime.us-east-1.amazonaws.com/model/us.anthropic.claude-sonnet-4-20250514-v1:0/invoke",
    "model": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "anthropic_version": "bedrock-2023-05-31",
    "messages": [{"role": "user", "content": "你好，请用一句话介绍你自己"}],
    "max_tokens": 200
  }'
```

### 2. Claude Sonnet 4.6 ✅

```bash
curl -X POST http://172.168.20.130:8080/default/passthrough \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer nd-c2dbf13988de84899ce461e812192d447eed5aed35244f85ba73bf65a2afccd6" \
  -d '{
    "channel": "aws",
    "channel_url": "https://bedrock-runtime.us-east-1.amazonaws.com/model/us.anthropic.claude-sonnet-4-6/invoke",
    "model": "us.anthropic.claude-sonnet-4-6",
    "anthropic_version": "bedrock-2023-05-31",
    "messages": [{"role": "user", "content": "你好，请用一句话介绍你自己"}],
    "max_tokens": 200
  }'
```

### 3. Claude Opus 4.6 ✅

```bash
curl -X POST http://172.168.20.130:8080/default/passthrough \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer nd-c2dbf13988de84899ce461e812192d447eed5aed35244f85ba73bf65a2afccd6" \
  -d '{
    "channel": "aws",
    "channel_url": "https://bedrock-runtime.us-east-1.amazonaws.com/model/us.anthropic.claude-opus-4-6-v1/invoke",
    "model": "us.anthropic.claude-opus-4-6-v1",
    "anthropic_version": "bedrock-2023-05-31",
    "messages": [{"role": "user", "content": "你好，请用一句话介绍你自己"}],
    "max_tokens": 200
  }'
```

### 4. Claude Opus 4.7 ✅

```bash
curl -X POST http://172.168.20.130:8080/default/passthrough \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer nd-c2dbf13988de84899ce461e812192d447eed5aed35244f85ba73bf65a2afccd6" \
  -d '{
    "channel": "aws",
    "channel_url": "https://bedrock-runtime.us-east-1.amazonaws.com/model/us.anthropic.claude-opus-4-7/invoke",
    "model": "us.anthropic.claude-opus-4-7",
    "anthropic_version": "bedrock-2023-05-31",
    "messages": [{"role": "user", "content": "你好，请用一句话介绍你自己"}],
    "max_tokens": 200
  }'
```

---

## 二、OpenAI 兼容接口 ✅

网关自动将 OpenAI 格式转换为 Anthropic 格式，发送到 Bedrock invoke API，再将响应转回 OpenAI 格式。
适合已有 OpenAI SDK 集成的场景，像调 OpenAI 一样使用。

**接口地址**：`POST /default/v1/chat/completions`

### 1. Claude Sonnet 4 ✅

```bash
curl -X POST http://172.168.20.130:8080/default/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer nd-c2dbf13988de84899ce461e812192d447eed5aed35244f85ba73bf65a2afccd6" \
  -d '{
    "model": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "messages": [{"role": "user", "content": "你好，请用一句话介绍你自己"}],
    "max_tokens": 200
  }'
```

### 2. Claude Sonnet 4.6 ✅

```bash
curl -X POST http://172.168.20.130:8080/default/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer nd-c2dbf13988de84899ce461e812192d447eed5aed35244f85ba73bf65a2afccd6" \
  -d '{
    "model": "us.anthropic.claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "你好，请用一句话介绍你自己"}],
    "max_tokens": 200
  }'
```

### 3. Claude Opus 4.6 ✅

```bash
curl -X POST http://172.168.20.130:8080/default/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer nd-c2dbf13988de84899ce461e812192d447eed5aed35244f85ba73bf65a2afccd6" \
  -d '{
    "model": "us.anthropic.claude-opus-4-6-v1",
    "messages": [{"role": "user", "content": "你好，请用一句话介绍你自己"}],
    "max_tokens": 200
  }'
```

### 4. Claude Opus 4.7 ✅

```bash
curl -X POST http://172.168.20.130:8080/default/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer nd-c2dbf13988de84899ce461e812192d447eed5aed35244f85ba73bf65a2afccd6" \
  -d '{
    "model": "us.anthropic.claude-opus-4-7",
    "messages": [{"role": "user", "content": "你好，请用一句话介绍你自己"}],
    "max_tokens": 200
  }'
```

### 5. 带 System Message ✅

```bash
curl -X POST http://172.168.20.130:8080/default/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer nd-c2dbf13988de84899ce461e812192d447eed5aed35244f85ba73bf65a2afccd6" \
  -d '{
    "model": "us.anthropic.claude-sonnet-4-6",
    "messages": [
      {"role": "system", "content": "你是一个专业的技术助手"},
      {"role": "user", "content": "什么是RESTful API？"}
    ],
    "max_tokens": 500
  }'
```

---

## 三、Python SDK 调用示例

```python
from openai import OpenAI

client = OpenAI(
    api_key="nd-c2dbf13988de84899ce461e812192d447eed5aed35244f85ba73bf65a2afccd6",
    base_url="http://172.168.20.130:8080/default/v1"
)

response = client.chat.completions.create(
    model="us.anthropic.claude-sonnet-4-6",
    messages=[
        {"role": "system", "content": "你是一个有帮助的助手"},
        {"role": "user", "content": "你好，请用一句话介绍你自己"}
    ],
    max_tokens=200
)

print(response.choices[0].message.content)
```

---

## 四、Cursor / IDE 配置

在 Cursor 或其他支持 OpenAI API 的工具中：

| 配置项 | 值 |
|--------|-----|
| API Base URL | `http://172.168.20.130:8080/default/v1` |
| API Key | `nd-c2dbf13988de84899ce461e812192d447eed5aed35244f85ba73bf65a2afccd6` |
| Model | `us.anthropic.claude-sonnet-4-6`（推荐） |

可选模型：`us.anthropic.claude-opus-4-7`、`us.anthropic.claude-opus-4-6-v1`

---

## 五、可用模型速查表

| 模型 | Model ID | 说明 | 状态 |
|------|----------|------|------|
| Claude Sonnet 4 | `us.anthropic.claude-sonnet-4-20250514-v1:0` | 经典稳定 | ✅ 已验证 |
| Claude Sonnet 4.6 | `us.anthropic.claude-sonnet-4-6` | 性价比高，1M上下文 | ✅ 已验证 |
| Claude Opus 4.6 | `us.anthropic.claude-opus-4-6-v1` | 最强推理，128K输出 | ✅ 已验证 |
| Claude Opus 4.7 | `us.anthropic.claude-opus-4-7` | 最新旗舰（4/16发布） | ✅ 已验证 |

> **注意**：
> - 模型 ID 格式不统一是 AWS Bedrock 的问题，请严格按上表使用
> - Opus 4.6 有 `-v1` 后缀，Sonnet 4.6 和 Opus 4.7 **没有**
> - Sonnet 4 有日期版本号 `-20250514-v1:0`
> - Sonnet 4.7 目前在 Bedrock 上**不可用**

---

## 六、测试验证记录

### 透传接口（Passthrough）

| 模型 | HTTP | 耗时 | input_tokens | output_tokens |
|------|------|------|-------------|---------------|
| Sonnet 4 | 200 | 1.35s | 9 | 4 |
| Sonnet 4.6 | 200 | 2.53s | 9 | 4 |
| Opus 4.6 | 200 | 1.90s | 9 | 4 |
| Opus 4.7 | 200 | 1.89s | 15 | 6 |

### OpenAI 兼容接口

| 模型 | HTTP | 耗时 | prompt_tokens | completion_tokens |
|------|------|------|--------------|-------------------|
| Sonnet 4 | 200 | 1.17s | 9 | 4 |
| Sonnet 4.6 | 200 | 1.87s | 9 | 4 |
| Opus 4.6 | 200 | 1.96s | 9 | 4 |
| Opus 4.7 | 200 | 1.22s | 15 | 6 |
| + system msg | 200 | 2.80s | 18 | 12 |
| + stream | 200 | 1.66s | 9 | 4 |

---

## 七、故障排查

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `The provided model identifier is invalid` | 模型 ID 格式错误 | 参照上方速查表 |
| `Access denied...Legacy` | 模型权限过期 | 去 AWS Bedrock 控制台重新开通 |
| `channel 'aws' not found or disabled` | 渠道未启用 | 在网关管理后台启用 aws 渠道 |
| `anthropic_version: Field required` | 透传缺少必填字段 | 请求体添加 `"anthropic_version": "bedrock-2023-05-31"` |
| `model: Extra inputs are not permitted` | 透传的 invoke 端点不接受 model 字段 | 网关已自动处理，使用最新版本 |

---

## 八、技术说明

- **透传接口**：请求原样转发到 Bedrock invoke API，返回 Anthropic 原生格式
- **OpenAI 兼容接口**：网关自动做格式转换（OpenAI → Anthropic → OpenAI），对客户端透明
- **流式输出**：OpenAI 兼容接口的 `stream: true` 会自动退化为非流式返回（Bedrock invoke 不支持标准 SSE），响应格式仍为标准 OpenAI 格式
- **system message**：OpenAI 兼容接口自动将 system 消息转换为 Anthropic 的 `system` 字段
