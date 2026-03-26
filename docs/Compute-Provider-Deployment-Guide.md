# Compute Provider Deployment Guide

> For administrators: how to configure compute clusters in NoDeskClaw so AI instances have somewhere to run.

---

## 1. Overview

NoDeskClaw uses a **Compute Provider** abstraction to manage the runtime environment for AI instances. A "cluster" is essentially an instance of a compute provider. Two types are currently supported:

| Compute Provider | Use Case | Credentials | Instance Runtime |
|---|---|---|---|
| `docker` | Local dev, small-scale trial | None (Docker daemon must be accessible) | One Docker Compose project per instance |
| `k8s` | Production, multi-instance | KubeConfig | Deployment + Service + Ingress |

> `process` (local subprocess) is registered but not wired into the standard deployment flow — reserved for future use.

### Architecture

```
User creates instance in Portal
        │
        ▼
  deploy_service routes by cluster type
        │
        ├── compute_provider == "docker"
        │       └── DockerComputeProvider
        │               └── docker compose up -d
        │
        └── compute_provider == "k8s"
                └── Built-in K8s deploy pipeline
                        └── Namespace → ConfigMap → PVC → Deployment → Service → Ingress
```

---

## 2. Docker Cluster (Local Dev / Trial)

### Prerequisites

- **Docker Engine** and **Docker Compose V2** installed on the host (`docker compose version` must work)
- The backend process can reach the Docker daemon (via Docker socket)

### 2.1 Docker Compose Deployment (Recommended)

The root `docker-compose.yml` comes pre-configured for Docker compute:

```yaml
nodeskclaw-backend:
  volumes:
    - type: bind
      source: /var/run/docker.sock
      target: /var/run/docker.sock
    - type: bind
      source: ${NODESKCLAW_DATA_DIR:-${OS:+${NODESKCLAW_DATA_DIR:?NODESKCLAW_DATA_DIR required on Windows}}${HOME:?HOME must be set on macOS/Linux}/.nodeskclaw/docker-instances}
      target: /nodeskclaw-data
  environment:
    DOCKER_DATA_DIR: /nodeskclaw-data
    DOCKER_HOST_DATA_DIR: ${NODESKCLAW_DATA_DIR:-${OS:+${NODESKCLAW_DATA_DIR:?NODESKCLAW_DATA_DIR required on Windows}}${HOME:?HOME must be set on macOS/Linux}/.nodeskclaw/docker-instances}
```

**Key volume mounts:**

| Mount | Purpose |
|---|---|
| `/var/run/docker.sock` | Allows `docker compose` inside the backend container to control the host Docker daemon |
| `NODESKCLAW_DATA_DIR` / `$HOME/.nodeskclaw/docker-instances` | Host instance data directory, mounted into the backend container at `/nodeskclaw-data` |

**Windows (Docker Desktop) note:**

macOS/Linux can use the default `$HOME/.nodeskclaw/docker-instances`. On Windows, `$HOME` is unreliable, so you must set `NODESKCLAW_DATA_DIR` in the project root `.env` to an absolute host path or Compose will fail immediately. Example:

```bash
NODESKCLAW_DATA_DIR=C:\Users\yourname\.nodeskclaw\docker-instances
```

After starting the platform, go to **Org Settings → Clusters** in the Portal, click "Add Cluster", and select **Docker**. The backend automatically runs `docker compose version` to verify the environment.

### 2.2 Local Development (`./dev.sh`)

When running locally, the backend runs directly on the host and can natively access the Docker daemon — no extra configuration needed.

When running the backend directly on the host, `DOCKER_DATA_DIR` defaults to `~/.nodeskclaw/docker-instances` when unset. In Docker Compose deployments, macOS/Linux default to `$HOME/.nodeskclaw/docker-instances`; Windows fails immediately if `NODESKCLAW_DATA_DIR` is missing, and `DOCKER_DATA_DIR` is fixed to `/nodeskclaw-data`.

### 2.3 How Docker Instances Work

When a Docker instance is created, the system:

1. **Allocates a host port** — starting from `13000`, incrementing to avoid conflicts with existing instances
2. **Generates a Compose file** — written to `{DOCKER_DATA_DIR}/{slug}/docker-compose.yml`
3. **Starts the container** — `docker compose -f <path> up -d`
4. **Persists data** — instance data is bound from `{DOCKER_HOST_DATA_DIR}/{slug}/data`, while the backend container accesses the same files at `{DOCKER_DATA_DIR}/{slug}/data`

Generated Compose file structure:

```yaml
services:
  agent:
    image: deskclaw:latest       # determined by deploy parameters
    container_name: my-instance
    ports:
      - "13000:18789"            # host port : container gateway port
    volumes:
      - type: bind
        source: /host/path/to/docker-instances/my-instance/data
        target: /root/.openclaw
    platform: linux/amd64
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
networks:
  my-instance-net:
    driver: bridge
```

### 2.4 Docker Instance Lifecycle

| Operation | Underlying Command |
|---|---|
| Create / Deploy | `docker compose -f <path> up -d` |
| Restart | `docker compose -f <path> restart` |
| View Logs | `docker logs --tail 50 <container>` |
| Scale | `docker compose -f <path> up -d --scale agent=N` |
| Delete | `docker compose -f <path> down -v` |
| Health Check | `docker inspect` + HTTP Probe |

### 2.5 Resource Limits & Auto-adaptation

- All instances share host resources; basic isolation via `mem_limit` / `cpus`
- **CPU auto-adaptation**: If the requested CPU count (default 2 cores) exceeds the host's available CPUs, the system automatically skips the CPU limit (i.e., no cap, uses all available CPUs) to prevent Docker daemon from rejecting container creation
- Instance URLs are `localhost:{port}` — no custom domains or HTTPS
- K8s-specific features are unavailable: cluster overview (node/CPU/memory stats), StorageClass selection, Pod Events, kubectl exec

---

## 3. Kubernetes Cluster (Production)

### Prerequisites

- A working Kubernetes cluster (v1.24+)
- A **KubeConfig** with sufficient permissions
- An **Ingress Controller** deployed in the cluster (default: nginx)
- **`ENCRYPTION_KEY`** configured in `.env` (used to encrypt stored KubeConfig)

### 3.1 KubeConfig Permission Requirements

NoDeskClaw requires the following K8s API permissions to manage instances:

| Resource | Verbs | Purpose |
|---|---|---|
| `namespaces` | create, get, delete | Each instance gets its own namespace |
| `deployments` | create, get, patch, delete, list | Instance container orchestration |
| `services` | create, get, delete | Network exposure |
| `ingresses` | create, get, delete | Domain routing (requires Ingress Controller) |
| `configmaps` | create, get, patch, delete | Instance configuration |
| `persistentvolumeclaims` | create, get, delete | Data persistence |
| `networkpolicies` | create, get, delete | Egress traffic control |
| `pods` | get, list, log | Status queries and logs |
| `nodes` | get, list | Cluster overview, connection test |
| `events` | list | Deployment event tracking |

> We recommend creating a dedicated ServiceAccount + ClusterRole for NoDeskClaw instead of using an admin kubeconfig.

### 3.2 Adding a K8s Cluster

In the Portal under **Org Settings → Clusters**:

1. Click "Add Cluster"
2. Select **Kubernetes** type
3. Choose a cloud vendor label (VKE / ACK / TKE / Custom) — UI label only, no functional impact
4. Paste the KubeConfig content
5. Set the Ingress Class (default `nginx`)
6. (Optional) Fill in Proxy Endpoint — for routing traffic through a gateway cluster
7. On submit, the system automatically runs a connection test (`VersionApi.get_code` + `list_node`)

### 3.3 KubeConfig Authentication Methods

The system auto-parses the KubeConfig and identifies the auth method:

| auth_type | Description | Notes |
|---|---|---|
| `token` | Static Bearer Token | Watch for token expiry |
| `client-certificate` | Client certificate auth | Renew KubeConfig when certificate expires |
| `exec-based` | External command for credentials | Backend environment must have the CLI tool installed |
| `oidc` | OpenID Connect | OIDC Provider must be reachable |

### 3.4 Cluster Configuration

Fields written to `provider_config` (JSONB) on cluster creation:

| Field | Description | Default |
|---|---|---|
| `cloud_vendor` | Cloud vendor label (vke/ack/tke/custom) | From request |
| `auth_type` | Auth method (auto-parsed) | — |
| `api_server_url` | K8s API Server address (auto-parsed) | — |
| `ingress_class` | Ingress Controller class name | `nginx` |
| `k8s_version` | K8s version (obtained during connection test) | — |

### 3.5 K8s Instance Deployment Pipeline

When a user creates an instance on a K8s cluster, the backend runs a full async pipeline:

```
① Create Namespace (nodeskclaw-default-{slug})
    ↓
② Create ConfigMap (instance configuration)
    ↓
③ Create PVC (persistent storage via StorageClass)
    ↓
④ Create Deployment (DeskClaw container)
    ↓
⑤ Create Service (ClusterIP)
    ↓
⑥ Create Ingress (domain routing)
    ↓
⑦ Create NetworkPolicy (egress traffic control)
    ↓
⑧ Wait for Pod Ready
    ↓
⑨ Post-deploy steps (LLM config sync, Gene installation, etc.)
```

### 3.6 K8s Infrastructure Requirements

#### Ingress Controller

Instances are exposed via Ingress for HTTP(S) access. The cluster must have a matching Ingress Controller:

- Default expectation: `ingressClassName: nginx`
- Customizable via `ingress_class` when creating the cluster
- See `nodeskclaw-artifacts/ingress-controller/` for deployment instructions

#### Storage (PVC)

Each instance creates a PVC for data persistence:

- Default StorageClass: uses the cluster's default SC (user can select manually when creating an instance)
- Default capacity: `80Gi`
- Adjustable via the create instance page

#### Network Policy

A NetworkPolicy is automatically created to control instance egress traffic. Related environment variables:

| Variable | Description | Example |
|---|---|---|
| `EGRESS_DENY_CIDRS` | Denied egress CIDR list | `10.0.0.0/8,172.16.0.0/12` |
| `EGRESS_ALLOW_PORTS` | Allowed egress port list | `443,80` |

---

## 4. Environment Variable Reference

### Common (All Compute Providers)

| Variable | Required | Description | Default |
|---|---|---|---|
| `ENCRYPTION_KEY` | Yes (for K8s) | KubeConfig encryption key (32 bytes, base64) | — |

### Docker-Specific

| Variable | Required | Description | Default |
|---|---|---|---|
| `DOCKER_DATA_DIR` | No | Backend working directory; fixed to `/nodeskclaw-data` in Compose deployments | `~/.nodeskclaw/docker-instances` |
| `DOCKER_HOST_DATA_DIR` | No | Host path used when the backend generates bind mounts for child containers | Same as `NODESKCLAW_DATA_DIR` or `$HOME/.nodeskclaw/docker-instances` |
| `NODESKCLAW_DATA_DIR` | Required on Windows | Compose host bind source path | macOS/Linux default: `$HOME/.nodeskclaw/docker-instances` |

### K8s-Specific

| Variable | Required | Description | Default |
|---|---|---|---|
| `VKE_SUBNET_ID` | For Volcengine VKE | VKE subnet ID | — |
| `EGRESS_DENY_CIDRS` | No | NetworkPolicy egress deny CIDRs | — |
| `EGRESS_ALLOW_PORTS` | No | NetworkPolicy egress allow ports | — |
| `IMAGE_REGISTRY` | No | Container image registry prefix | — |

---

## 5. Cluster Management API

| Method | Path | Description | Docker/K8s |
|---|---|---|---|
| `POST` | `/clusters` | Create cluster | Both |
| `GET` | `/clusters` | List clusters | Both |
| `GET` | `/clusters/{id}` | Cluster details | Both |
| `PUT` | `/clusters/{id}` | Update cluster info | Both |
| `DELETE` | `/clusters/{id}` | Delete cluster (cascading soft-delete of instances) | Both |
| `POST` | `/clusters/{id}/test` | Test connection | Both (Docker: verify compose; K8s: verify API Server) |
| `POST` | `/clusters/{id}/kubeconfig` | Update KubeConfig | K8s only |
| `GET` | `/clusters/{id}/overview` | Cluster resource overview (nodes/CPU/memory) | K8s only |
| `GET` | `/clusters/{id}/health` | Cluster health status | K8s only |

### Create Cluster Request Examples

Docker cluster:

```json
{
  "name": "Local Docker",
  "compute_provider": "docker"
}
```

K8s cluster:

```json
{
  "name": "Production Cluster",
  "compute_provider": "k8s",
  "kubeconfig": "apiVersion: v1\nkind: Config\n...",
  "provider": "vke",
  "ingress_class": "nginx"
}
```

---

## 6. Proxy Endpoint (Optional, Gateway Proxy)

For scenarios where the instance cluster is not directly exposed to the public internet. When configured, the system creates an ExternalName Service on the **gateway cluster** to proxy traffic to the instance cluster.

```
User Browser → Gateway Cluster Ingress → ExternalName Service → Instance Cluster
```

- Set `proxy_endpoint` when creating or updating a cluster
- The gateway cluster KubeConfig is configured via the `GATEWAY_KUBECONFIG` environment variable

---

## 7. Troubleshooting

### Docker cluster creation failed: cannot connect to Docker daemon

**Cause**: The backend cannot access the Docker socket.

**Steps**:
1. Docker Compose deployment: verify `/var/run/docker.sock` is correctly mounted in `docker-compose.yml`
2. Running directly on host: verify the current user is in the `docker` group
3. Test command: `docker compose version`

### K8s cluster connection test failed

**Steps**:
1. Verify the API Server address in the KubeConfig is reachable from the backend network
2. Verify credentials have not expired (Token / certificate)
3. Verify `ENCRYPTION_KEY` is configured correctly (mismatched keys will fail to decrypt the KubeConfig)

### Docker deployment failed: Error response from daemon: range of CPUs

**Cause**: Requested CPU count exceeds the host's available CPUs. Older versions used a fixed default of `cpus: 2.0`, which fails on single-core machines.

**Fix**: Upgrade to a version with CPU auto-adaptation. The system automatically detects available CPUs and skips limits that exceed the host capacity.

### Docker instance inaccessible

**Cause**: Port conflict or Docker networking issue.

**Steps**:
1. Check if the assigned port (starting from 13000) is occupied by another process on the host
2. Check container status: `docker ps -a | grep <slug>`
3. View container logs: `docker logs <slug>`

### K8s instance stuck in "Deploying"

**Steps**:
1. Check Pod status: `kubectl get pods -n nodeskclaw-default-<slug>`
2. Check Events: `kubectl describe pod <pod-name> -n <namespace>`
3. Common causes: image pull failure (ImagePullBackOff), insufficient resources (Pending), PVC binding failure
