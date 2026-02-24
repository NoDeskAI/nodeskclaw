# openclaw-channel-learning

OpenClaw channel plugin for ClawBuddy Gene Evolution Ecosystem.

## Overview

This plugin handles two types of asynchronous tasks:

- **Learn mode**: Agent evaluates and learns a gene, producing a personalized SKILL.md
- **Create mode**: Agent creates a new gene from work experience

## How it works

1. ClawBuddy backend POSTs a learning/creation task to the plugin's webhook endpoint
2. Plugin injects the task as a message into the Agent's context
3. Agent processes the task and responds via the `send` tool
4. Plugin forwards the result to ClawBuddy backend's callback URL

## Directory Structure

```
openclaw-channel-learning/
  index.ts              # Plugin entry point, webhook registration
  package.json          # Package configuration
  openclaw.plugin.json  # Plugin manifest
  src/
    channel.ts          # Channel plugin (learn + create modes)
    runtime.ts          # Runtime reference
    types.ts            # TypeScript type definitions
```

## Webhook API

`POST /extensions/learning/webhook`

```json
{
  "mode": "learn",
  "task_id": "uuid",
  "gene_slug": "code-review",
  "gene_content": "SKILL.md content",
  "learning": { "objectives": [...], "scenarios": [...] },
  "callback_url": "https://backend/api/v1/genes/learning-callback"
}
```
