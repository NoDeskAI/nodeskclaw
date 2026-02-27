# openclaw-channel-learning

OpenClaw channel plugin for NoDeskClaw Gene Evolution Ecosystem.

## Overview

This plugin handles three types of asynchronous tasks:

- **Learn mode**: Agent evaluates and learns a gene, producing a personalized SKILL.md
- **Create mode**: Agent creates a new gene from work experience
- **Forget mode**: Agent reviews experience with a gene, producing a forgetting summary or a simplified skill

## How it works

1. NoDeskClaw backend POSTs a task to the plugin's webhook endpoint
2. Plugin injects the task as a message into the Agent's context
3. Agent processes the task and responds via the `send` tool
4. Plugin forwards the result to NoDeskClaw backend's callback URL

## Directory Structure

```
openclaw-channel-learning/
  index.ts              # Plugin entry point, webhook registration
  package.json          # Package configuration
  openclaw.plugin.json  # Plugin manifest
  src/
    channel.ts          # Channel plugin (learn + create + forget modes)
    runtime.ts          # Runtime reference
    types.ts            # TypeScript type definitions
```

## Webhook API

`POST /extensions/learning/webhook`

### Learn mode

```json
{
  "mode": "learn",
  "task_id": "uuid",
  "gene_slug": "code-review",
  "gene_content": "SKILL.md content",
  "learning": { "objectives": ["..."], "scenarios": ["..."] },
  "callback_url": "https://backend/api/v1/genes/learning-callback"
}
```

### Forget mode

```json
{
  "mode": "forget",
  "task_id": "uuid",
  "gene_slug": "code-review",
  "gene_content": "current SKILL.md content",
  "learning_output": "Agent's personalized learning (if any)",
  "usage_count": 42,
  "callback_url": "https://backend/api/v1/genes/forgetting-callback"
}
```

Agent responds with one of:

- `decision: "forgotten"` -- complete forget, content is a summary of insights
- `decision: "simplified"` -- partial forget, content is a reduced SKILL.md
- `decision: "forget_failed"` -- unable to process
