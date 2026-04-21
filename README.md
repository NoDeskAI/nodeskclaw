[中文](README.zh-CN.md)

[Discord](https://discord.gg/y5NKqcP6eY)
[License](LICENSE)

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

Instant expansion of operating capacity. One-click deployment of AI operating partners on Kubernetes clusters. Local development supported via `dev.sh` for rapid iteration.

## Highlights

- **Cyber Workspace** -- Hexagonal topology space where human and AI partners co-operate, share an operations board, and delegate tasks
- **Gene System** -- Modular capability investment: load new business dimensions onto AI partners from a public or private marketplace
- **One-Click Scale** -- Expand your operating capacity end-to-end, with SSE real-time progress streaming
- **Multi-Cluster Operations** -- Cross-cluster orchestration, health checks, and elastic scaling across your business footprint

## Architecture

```mermaid
flowchart LR
    subgraph ops [" Co-operators "]
        direction TB
        Human["Human Operators<br>Strategy · Judgment"]
        AI["AI Partners<br>Execution · Iteration"]
        Human <-.->|co-operate| AI
    end

    ops --> channels

    subgraph channels [" Channels "]
        direction TB
        Portal["Web Portal"]
        DingTalk["DingTalk"]
        OpenAPI["Open API"]
    end

    channels --> coopCore

    subgraph coopCore [" Co-operation Core "]
        direction TB
        subgraph cyberWS [" Cyber Workspace "]
            direction LR
            Topo["Hex Topology"]
            Board["Shared Blackboard"]
            Tasks["Task Delegation"]
        end
        subgraph geneSys [" Gene System "]
            direction LR
            Market["Marketplace"]
            EntLib["Enterprise Library"]
        end
    end

    coopCore --> platform

    subgraph platform [" Platform Services "]
        direction TB
        Instance["Instance Lifecycle"]
        Cluster["Multi-Cluster"]
        Scale["Elastic Scale"]
        LLMProxy["LLM Routing"]
        ChPlugin["Channel Plugins"]
    end

    platform --> infra

    subgraph infra [" Infrastructure "]
        direction TB
        K8s["Kubernetes"]
        Runtime["OpenClaw / Nanobot"]
        DB["PostgreSQL"]
        LLMs["OpenAI · Anthropic · Gemini · ..."]
    end
```



### Project Layout

```
DeskClaw/
├── nodeskclaw-portal/             # User Portal -- Vue 3 + Tailwind CSS
├── nodeskclaw-backend/            # API Server -- Python 3.12 + FastAPI + SQLAlchemy
├── nodeskclaw-llm-proxy/          # LLM Proxy -- Python + FastAPI
├── nodeskclaw-artifacts/          # Docker images & deploy manifests
├── openclaw-channel-nodeskclaw/   # Cyber Workspace channel plugin
├── openclaw-channel-dingtalk/     # DingTalk channel plugin (Stream protocol)
├── openclaw/                      # DeskClaw runtime source (external)
└── vibecraft/                     # VibeCraft source (external)
```

## i18n

Full-stack internationalization covering Portal and Backend.

- Language detection: `zh*` -> `zh-CN`, `en*` -> `en-US`, fallback `en-US`
- Error display: prefer `message_key` local translation, fall back to `message` when missing
- Backend contract: `code` + `error_code` + `message_key` + `message` + `data`

## Quick Start

### Kubernetes (recommended)

DeskClaw is designed to run on Kubernetes. K8s is the primary deployment target for both staging and production. For local development, use `dev.sh` instead (see below).

Requires a K8s cluster, a container registry, and an external PostgreSQL database.

#### Prerequisites


| Dependency         |                                                         |
| ------------------ | ------------------------------------------------------- |
| Kubernetes cluster | 1.24+ with Ingress Controller (e.g. ingress-nginx)      |
| Container registry | Any Docker V2 registry (Docker Hub, AWS ECR, GCR, etc.) |
| PostgreSQL         | External database (e.g. AWS RDS, GCP Cloud SQL)         |
| kubectl            | Configured with access to your cluster                  |
| Docker             | For building images locally                             |


#### 1. Configure Registry & Context

```bash
# Create deploy/.env.local (git-ignored)
cat > deploy/.env.local <<'EOF'
REGISTRY="your-registry.example.com/deskclaw"
KUBE_CONTEXT="your-kubectl-context"
EOF

# Login to your container registry
docker login your-registry.example.com
```

#### 2. Prepare Backend Environment Variables

```bash
cp nodeskclaw-backend/.env.example nodeskclaw-backend/.env
# Edit .env -- fill in DATABASE_URL, JWT_SECRET, ENCRYPTION_KEY, etc.
# Minimum required:
#   DATABASE_URL=postgresql+asyncpg://user:pass@your-rds:5432/nodeskclaw
#   JWT_SECRET=<random-secret>
#   ENCRYPTION_KEY=<32-byte-base64-key>
```

#### 3. Initialize the Cluster

Creates the namespace, uploads `.env` as a K8s Secret, and applies base Deployment + Service manifests:

```bash
./deploy/cli.sh init                    # Default: staging namespace
./deploy/cli.sh init --prod             # Production namespace
```

#### 4. Build & Deploy

```bash
./deploy/cli.sh deploy                  # Build all images + rolling update (staging)
./deploy/cli.sh deploy --prod           # Deploy to production (interactive confirm)
./deploy/cli.sh deploy backend          # Deploy a single component
```

#### 5. Configure Ingress

Edit `deploy/k8s/ingress.yaml` -- replace `example.com` hosts with your actual domains, then apply:

```bash
kubectl --context <CTX> -n <NS> apply -f deploy/k8s/ingress.yaml
```

The Ingress defines two hosts (configure as needed):


| Ingress   | Default host            | Backend service                  |
| --------- | ----------------------- | -------------------------------- |
| Portal    | `console.example.com`   | portal (80) + backend API (8000) |
| LLM Proxy | `llm-proxy.example.com` | llm-proxy (80)                   |


See [deploy/README.md](deploy/README.md) for full CLI reference, image tagging, and the release/promote workflow.

### Local Development

#### Prerequisites


| Dependency                                        |                                       |
| ------------------------------------------------- | ------------------------------------- |
| Python >= 3.12 + [uv](https://docs.astral.sh/uv/) | Backend runtime & package manager     |
| Node.js >= 18 + npm                               | Frontend runtime                      |
| PostgreSQL                                        | Database (or use `--docker-pg` below) |


#### 1. Configure

```bash
cd nodeskclaw-backend
cp .env.example .env
# Edit .env -- fill in DATABASE_URL, JWT_SECRET, etc.
```

#### 2. One-command Start

```bash
./dev.sh              # Start all services (backend + portal)
./dev.sh --docker-pg  # Start a Docker PostgreSQL (no local PG install needed)
./dev.sh --fresh      # Force reinstall all dependencies
```

The script handles dependency installation, starts all services with colored log prefixes, and cleans up on Ctrl+C. `--docker-pg` launches a local PostgreSQL container automatically.

Services: backend (4510) + llm-proxy (4511) + portal (4517)

Manual Start (alternative)

**Backend:**

```bash
cd nodeskclaw-backend
uv sync
uv run uvicorn app.main:app --reload --port 4510
```

API at `http://localhost:4510` | Swagger at `http://localhost:4510/docs` | Auto-migration on first boot.

**Frontend (Portal):**

```bash
cd nodeskclaw-portal
npm install && npm run dev
```

Portal at `http://localhost:4517` | `/api` auto-proxy to backend.



#### 3. Sign In

On first startup the backend prints the initial admin credentials directly in the terminal output:

```
========================================
  Initial admin account
  Account: admin
  Password: <random>
  Please change your password after login
========================================
```

Open `http://localhost:4517` and sign in with the printed credentials. You will be prompted to change the password on first login.

## Upgrade

### Kubernetes

K8s deployments are managed by `deploy/cli.sh`. The typical workflow is **deploy to staging first, then promote to production**.

**Staging** -- build images, push to registry, and rolling-update the staging namespace:

```bash
./deploy/cli.sh deploy --tag v0.9.0
```

**Production** -- reuse the already-pushed images and update the production namespace (no rebuild):

```bash
./deploy/cli.sh promote v0.9.0
```

Database migrations run automatically when the new backend pod starts. See [deploy/README.md](deploy/README.md) for full CLI usage and options.

### Docker Compose

For quick self-hosted deployment without Kubernetes:

```bash
docker compose up -d                   # CE mode (default)
docker compose up -d --build           # Rebuild images
```

### Build Mirrors

If pulling dependencies (PyPI, npm, Debian/Alpine packages) is slow in your region, use a mirror preset to speed up builds:

```bash
# deploy/cli.sh
./deploy/cli.sh deploy --mirrors cn

# docker compose
docker compose --env-file deploy/mirrors/cn.env up -d --build

# artifacts (DeskClaw engine images)
./nodeskclaw-artifacts/build.sh openclaw --mirrors cn
```

Available presets are in `deploy/mirrors/`. See [deploy/mirrors/README.md](deploy/mirrors/README.md) for details and customization.

> **Note:** Docker Hub base image pulls (`FROM python:3.12-slim`, etc.) cannot be accelerated this way. Configure a [registry mirror](https://docs.docker.com/docker-hub/mirror/) in your Docker daemon instead.

### Upgrade Notes

- **Back up your database** before any major version upgrade.
- Check [GitHub Releases](https://github.com/NoDeskAI/nodeskclaw/releases) for release notes and breaking changes.
- If your database was not previously managed by Alembic, you may need to run `alembic stamp head` once before upgrading. See [Backend README](nodeskclaw-backend/README.md) for details.

## Documentation


|                                                         |                                              |
| ------------------------------------------------------- | -------------------------------------------- |
| [Backend](nodeskclaw-backend/README.md)                 | API hub, directory layout, env vars          |
| [Portal](nodeskclaw-portal/README.md)                   | User portal frontend                         |
| [Artifacts](nodeskclaw-artifacts/README.md)             | DeskClaw image build & deploy manifests      |
| [Channel Plugin](openclaw-channel-nodeskclaw/README.md) | Cyber Workspace communication infrastructure |
| [DingTalk Plugin](openclaw-channel-dingtalk/README.md)  | DingTalk channel via Stream protocol         |
| [LLM Proxy](nodeskclaw-llm-proxy/README.md)             | AI reasoning capability relay                |


## Community

- [Discord](https://discord.gg/y5NKqcP6eY) -- Join the discussion, ask questions, share feedback
- [GitHub Issues](https://github.com/NoDeskAI/nodeskclaw/issues) -- Bug reports and feature requests
- WeChat -- Scan the QR code below to join the developer group; if the WeChat group is full, please use Discord above

<img src="docs/assets/wechat-group-qr.png" alt="WeChat Group QR Code" width="200" />

## Contributing

PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[Apache License 2.0](LICENSE)