# Compute Provider Deployment Guide

> For administrators: how to configure compute clusters in NoDeskClaw so AI instances have somewhere to run.

---

## 1. Overview

NoDeskClaw uses a **Compute Provider** abstraction to manage the runtime environment for AI instances. A "cluster" is essentially an instance of a compute provider. Kubernetes is the supported compute provider for instance deployment:

| Compute Provider | Use Case | Credentials | Instance Runtime |
|---|---|---|---|
| `k8s` | Production, multi-instance | KubeConfig | Deployment + Service + Ingress |

> `process` (local subprocess) is registered but not wired into the standard deployment flow — reserved for future use.

### Architecture

```
User creates instance in Portal
        │
        ▼
  deploy_service routes by cluster type
        │
        └── compute_provider == "k8s"
                └── Built-in K8s deploy pipeline
                        └── Namespace → ConfigMap → PVC → Deployment → Service → Ingress
```

---

## 2. Kubernetes Cluster

### Prerequisites

- A working Kubernetes cluster (v1.24+)
- A **KubeConfig** with sufficient permissions
- An **Ingress Controller** deployed in the cluster (default: nginx)
- **`ENCRYPTION_KEY`** configured in `.env` (used to encrypt stored KubeConfig)

### 2.1 KubeConfig Permission Requirements

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

### 2.2 Adding a K8s Cluster

In the Portal under **Org Settings → Clusters**:

1. Click "Add Cluster"
2. Select **Kubernetes** type
3. Choose a cloud vendor label (VKE / ACK / TKE / Custom) — UI label only, no functional impact
4. Paste the KubeConfig content
5. Set the Ingress Class (default `nginx`)
6. (Optional) Fill in Proxy Endpoint — for routing traffic through a gateway cluster
7. On submit, the system automatically runs a connection test (`VersionApi.get_code` + `list_node`)

### 2.3 KubeConfig Authentication Methods

The system auto-parses the KubeConfig and identifies the auth method:

| auth_type | Description | Notes |
|---|---|---|
| `token` | Static Bearer Token | Watch for token expiry |
| `client-certificate` | Client certificate auth | Renew KubeConfig when certificate expires |
| `exec-based` | External command for credentials | Backend environment must have the CLI tool installed |
| `oidc` | OpenID Connect | OIDC Provider must be reachable |

### 2.4 Cluster Configuration

Fields written to `provider_config` (JSONB) on cluster creation:

| Field | Description | Default |
|---|---|---|
| `cloud_vendor` | Cloud vendor label (vke/ack/tke/custom) | From request |
| `auth_type` | Auth method (auto-parsed) | — |
| `api_server_url` | K8s API Server address (auto-parsed) | — |
| `ingress_class` | Ingress Controller class name | `nginx` |
| `k8s_version` | K8s version (obtained during connection test) | — |

### 2.5 K8s Instance Deployment Pipeline

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

### 2.6 K8s Infrastructure Requirements

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

## 3. Environment Variable Reference

| Variable | Required | Description | Default |
|---|---|---|---|
| `ENCRYPTION_KEY` | Yes | KubeConfig encryption key (32 bytes, base64) | — |
| `VKE_SUBNET_ID` | For Volcengine VKE | VKE subnet ID | — |
| `EGRESS_DENY_CIDRS` | No | NetworkPolicy egress deny CIDRs | — |
| `EGRESS_ALLOW_PORTS` | No | NetworkPolicy egress allow ports | — |
| `IMAGE_REGISTRY` | No | Container image registry prefix | — |

---

## 4. Cluster Management API

| Method | Path | Description |
|---|---|---|
| `POST` | `/clusters` | Create cluster |
| `GET` | `/clusters` | List clusters |
| `GET` | `/clusters/{id}` | Cluster details |
| `PUT` | `/clusters/{id}` | Update cluster info |
| `DELETE` | `/clusters/{id}` | Delete cluster (cascading soft-delete of instances) |
| `POST` | `/clusters/{id}/test` | Test connection (verify API Server) |
| `POST` | `/clusters/{id}/kubeconfig` | Update KubeConfig |
| `GET` | `/clusters/{id}/overview` | Cluster resource overview (nodes/CPU/memory) |
| `GET` | `/clusters/{id}/health` | Cluster health status |

### Create Cluster Request Example

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

## 5. Proxy Endpoint (Optional, Gateway Proxy)

For scenarios where the instance cluster is not directly exposed to the public internet. When configured, the system creates an ExternalName Service on the **gateway cluster** to proxy traffic to the instance cluster.

```
User Browser → Gateway Cluster Ingress → ExternalName Service → Instance Cluster
```

- Set `proxy_endpoint` when creating or updating a cluster
- The gateway cluster KubeConfig is configured via the `GATEWAY_KUBECONFIG` environment variable

---

## 6. Troubleshooting

### K8s cluster connection test failed

**Steps**:
1. Verify the API Server address in the KubeConfig is reachable from the backend network
2. Verify credentials have not expired (Token / certificate)
3. Verify `ENCRYPTION_KEY` is configured correctly (mismatched keys will fail to decrypt the KubeConfig)

### K8s instance stuck in "Deploying"

**Steps**:
1. Check Pod status: `kubectl get pods -n nodeskclaw-default-<slug>`
2. Check Events: `kubectl describe pod <pod-name> -n <namespace>`
3. Common causes: image pull failure (ImagePullBackOff), insufficient resources (Pending), PVC binding failure
