[中文](README.zh-CN.md)

# DeskClaw

**Co-operate with AI.** The open-source platform where humans and AI run businesses together -- from strategy to execution.

DeskClaw is the operating platform for human-AI co-managed organizations. Through Cyber Workspaces, humans and AI operate as partners in a shared digital space -- humans provide strategic judgment, AI delivers relentless execution, and together they build something neither could alone.

## Co-operating

We believe the future belongs to organizations where humans and AI co-operate -- not as master and tool, but as partners who each bring irreplaceable value to the business.

- **Human operators** bring strategic judgment, creative decisions, and value alignment -- deciding *what to do* and *why*
- **AI operators** bring tireless execution, pattern recognition, and rapid iteration -- pushing *how to do it* to the extreme
- **Cyber Workspace** is where co-operating happens -- a shared operations board (blackboard), task delegation, and real-time coordination that fuses human and AI capabilities into one

## Core Concepts

### Cyber Workspace

The digital space where humans and AI co-operate. Hexagonal topology visualizes your operating team's relationships; the shared blackboard serves as the team's operations dashboard; task publishing lets any partner -- human or AI -- delegate work to whoever is best suited. Not a monitoring panel, but the place where business happens.

### Gene System

Investment in AI operating capabilities. Loading a new Gene onto an AI partner opens a new dimension for your business -- modular capability packages from a public marketplace or your private enterprise library, composable on demand, continuously evolving. The business you run determines the Genes you load.

### Elastic Scale

Instant expansion of operating capacity. One-click deployment of AI operating partners on Kubernetes clusters or local Docker environments. DeskClaw handles the infrastructure so you can focus on operating decisions.

## Highlights

- **Cyber Workspace** -- Hexagonal topology space where human and AI partners co-operate, share an operations board, and delegate tasks
- **Gene System** -- Modular capability investment: load new business dimensions onto AI partners from a public or private marketplace
- **One-Click Scale** -- Expand your operating capacity end-to-end, with SSE real-time progress streaming
- **Multi-Cluster Operations** -- Cross-cluster orchestration, health checks, and elastic scaling across your business footprint
- **Enterprise Auth** -- Feishu SSO with automatic org structure sync, bringing your existing organization into the platform

## CE / EE

Dual-edition architecture: Community Edition / Enterprise Edition.

| | CE (Community) | EE (Enterprise) |
|---|---|---|
| License | Apache 2.0 | Commercial |
| Features | Instance deploy, cluster management, log monitoring, gene marketplace | All of CE + multi-org, billing, advanced audit |
| Code | This repository | Private `ee/` directory |

Runtime auto-detection via `FeatureGate` -- if `ee/` exists it runs as EE, otherwise CE. Feature registry defined in `features.yaml`.

**Technical implementation**: Backend Factory abstraction + Hook event bus; Frontend Stub + Vite Alias Override.

## Architecture

```
DeskClaw/
├── nodeskclaw-portal/             # User Portal -- Vue 3 + Tailwind CSS (CE + EE)
├── nodeskclaw-backend/            # API Server -- Python 3.12 + FastAPI + SQLAlchemy
├── nodeskclaw-llm-proxy/          # LLM Proxy -- Python + FastAPI
├── nodeskclaw-artifacts/          # Docker images & deploy manifests
├── openclaw-channel-nodeskclaw/   # Cyber Workspace channel plugin
├── features.yaml                  # CE/EE feature registry
├── ee/                            # Enterprise Edition (private)
│   └── nodeskclaw-frontend/      # Admin Console -- Vue 3 + shadcn-vue (EE-only)
├── openclaw/                      # DeskClaw runtime source (external)
└── vibecraft/                     # VibeCraft source (external)
```

## i18n

Full-stack internationalization covering Portal, Admin, and Backend.

- Language detection: `zh*` -> `zh-CN`, `en*` -> `en-US`, fallback `en-US`
- Error display: prefer `message_key` local translation, fall back to `message` when missing
- Backend contract: `code` + `error_code` + `message_key` + `message` + `data`

## Quick Start

### Prerequisites

| Dependency | |
|---|---|
| Python >= 3.12 + [uv](https://docs.astral.sh/uv/) | Backend runtime & package manager |
| Node.js >= 18 + npm | Frontend runtime |
| PostgreSQL | Database |
| Feishu App | SSO (App ID + App Secret) |

### 1. Configure

```bash
cd nodeskclaw-backend
cp .env.example .env
# Edit .env -- fill in the required values below
```

| Variable | Description |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `JWT_SECRET` | JWT signing key |
| `ENCRYPTION_KEY` | KubeConfig AES key (32-byte base64) |
| `FEISHU_APP_ID` | Feishu App ID |
| `FEISHU_APP_SECRET` | Feishu App Secret |
| `FEISHU_REDIRECT_URI` | `http://localhost:4518/api/v1/auth/feishu/callback` |

### 2. One-command Start

```bash
./dev.sh          # Auto-detect: ee/ exists -> EE, otherwise -> CE
./dev.sh ce       # Force CE mode (backend + portal)
./dev.sh ee       # Force EE mode (backend + portal + admin)
./dev.sh --fresh  # Force reinstall all dependencies
```

The script handles dependency installation, starts all services with colored log prefixes, and cleans up on Ctrl+C.

| Mode | Services | Ports |
|------|----------|-------|
| CE | backend + portal | 8000, 4517 |
| EE | backend + portal + admin | 8000, 4517, 4518 |

### Manual Start (alternative)

<details>
<summary>Start each service individually</summary>

**Backend:**

```bash
cd nodeskclaw-backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

API at `http://localhost:8000` | Swagger at `http://localhost:8000/docs` | Auto-migration on first boot.

**Frontend (Portal):**

```bash
cd nodeskclaw-portal
npm install && npm run dev
```

Portal at `http://localhost:4517` | `/api` auto-proxy to backend.

**Frontend (Admin, EE-only):**

```bash
cd ee/nodeskclaw-frontend
npm install && npm run dev
```

Admin at `http://localhost:4518` | `/api` and `/stream` auto-proxy to backend.

</details>

### 3. Go

Open `http://localhost:4517` (Portal) or `http://localhost:4518` (Admin, EE), sign in.

> Feishu redirect URL: `http://localhost:4518/api/v1/auth/feishu/callback`

## Documentation

| | |
|---|---|
| [Backend](nodeskclaw-backend/README.md) | API hub, directory layout, env vars |
| [Portal](nodeskclaw-portal/README.md) | User portal frontend |
| [Artifacts](nodeskclaw-artifacts/README.md) | DeskClaw image build & deploy manifests |
| [Channel Plugin](openclaw-channel-nodeskclaw/README.md) | Cyber Workspace communication infrastructure |
| [LLM Proxy](nodeskclaw-llm-proxy/README.md) | AI reasoning capability relay |

## Contributing

PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[Apache License 2.0](LICENSE)
