"""K8sClient: single-cluster operation wrapper around kubernetes-asyncio."""

import logging
from datetime import datetime, timezone
from typing import AsyncIterator

from kubernetes_asyncio import client as k8s_client, watch
from kubernetes_asyncio.stream import WsApiClient

logger = logging.getLogger(__name__)


class _ExecWsApiClient(WsApiClient):
    """WsApiClient that returns raw exec output without JSON auto-parsing.

    kubernetes_asyncio's ApiClient.deserialize() calls json.loads() on the
    response body before converting to the target type.  When exec stdout
    happens to be valid JSON (e.g. ``cat openclaw.json``), the library
    parses it into a Python dict then str(dict) — producing single-quoted
    keys and Python booleans, which is NOT valid JSON.

    This subclass short-circuits that path for ``str`` return types so the
    raw stdout bytes are returned as-is.
    """

    def deserialize(self, response, response_type):
        if response_type == "str":
            data = response.data
            return data if isinstance(data, str) else data.decode("utf-8")
        return super().deserialize(response, response_type)


class K8sClient:
    """Wraps kubernetes-asyncio APIs for a single cluster."""

    def __init__(self, api_client: k8s_client.ApiClient):
        self._api = api_client
        self.core = k8s_client.CoreV1Api(api_client)
        self.apps = k8s_client.AppsV1Api(api_client)
        self.networking = k8s_client.NetworkingV1Api(api_client)
        self.version_api = k8s_client.VersionApi(api_client)
        self.custom = k8s_client.CustomObjectsApi(api_client)

    # ── Cluster-level ────────────────────────────────

    async def test_connection(self) -> dict:
        info = await self.version_api.get_code()
        return {"version": info.git_version, "platform": info.platform}

    async def get_cluster_overview(self) -> dict:
        nodes = await self.core.list_node()
        pods = await self.core.list_pod_for_all_namespaces()

        node_count = len(nodes.items)
        node_ready = sum(
            1
            for n in nodes.items
            if any(c.type == "Ready" and c.status == "True" for c in (n.status.conditions or []))
        )

        cpu_total = 0
        mem_total = 0
        for n in nodes.items:
            alloc = n.status.allocatable or {}
            cap = n.status.capacity or {}
            raw_cpu = alloc.get("cpu") or cap.get("cpu") or "0"
            raw_mem = alloc.get("memory") or cap.get("memory") or "0"
            logger.debug(
                "Node %s: raw_cpu=%s, raw_mem=%s",
                n.metadata.name, raw_cpu, raw_mem,
            )
            cpu_total += _parse_cpu(str(raw_cpu))
            mem_total += _parse_memory(str(raw_mem))

        cpu_used = 0
        mem_used = 0
        try:
            metrics_data = await self.custom.list_cluster_custom_object(
                "metrics.k8s.io", "v1beta1", "nodes"
            )
            for item in metrics_data.get("items", []):
                usage = item.get("usage", {})
                cpu_used += _parse_cpu(usage.get("cpu", "0"))
                mem_used += _parse_memory(usage.get("memory", "0"))
        except Exception:
            logger.warning("metrics-server unavailable, falling back to request-based estimation")
            for pod in pods.items:
                if pod.status.phase not in ("Running", "Pending"):
                    continue
                for c in (pod.spec.containers or []):
                    req = (c.resources.requests or {}) if c.resources else {}
                    cpu_used += _parse_cpu(req.get("cpu", "0"))
                    mem_used += _parse_memory(req.get("memory", "0"))

        logger.info(
            "Cluster overview: cpu_total=%sm, cpu_used=%sm, mem_total=%sMi, mem_used=%sMi",
            cpu_total, cpu_used, mem_total, mem_used,
        )

        return {
            "node_count": node_count,
            "node_ready": node_ready,
            "cpu_total": f"{cpu_total}m",
            "cpu_used": f"{cpu_used}m",
            "cpu_percent": round(cpu_used / max(cpu_total, 1) * 100, 1),
            "memory_total": f"{mem_total}Mi",
            "memory_used": f"{mem_used}Mi",
            "memory_percent": round(mem_used / max(mem_total, 1) * 100, 1),
            "pod_count": len(pods.items),
        }

    async def list_nodes(self) -> list[dict]:
        """列出集群所有节点及其资源使用概况。"""
        nodes = await self.core.list_node()
        # 尝试获取 metrics
        node_metrics: dict[str, dict] = {}
        try:
            metrics_data = await self.custom.list_cluster_custom_object(
                "metrics.k8s.io", "v1beta1", "nodes"
            )
            for item in metrics_data.get("items", []):
                name = item["metadata"]["name"]
                usage = item.get("usage", {})
                node_metrics[name] = {
                    "cpu_used": _parse_cpu(usage.get("cpu", "0")),
                    "mem_used": _parse_memory(usage.get("memory", "0")),
                }
        except Exception:
            pass  # metrics-server may not be available

        results = []
        for n in nodes.items:
            name = n.metadata.name
            conditions = n.status.conditions or []
            is_ready = any(c.type == "Ready" and c.status == "True" for c in conditions)
            addresses = n.status.addresses or []
            internal_ip = next(
                (a.address for a in addresses if a.type == "InternalIP"), None
            )

            cpu_cap = _parse_cpu(n.status.capacity.get("cpu", "0"))
            mem_cap = _parse_memory(n.status.capacity.get("memory", "0"))

            metrics = node_metrics.get(name, {})

            results.append({
                "name": name,
                "status": "Ready" if is_ready else "NotReady",
                "ip": internal_ip,
                "cpu_capacity": f"{cpu_cap}m",
                "cpu_used": f"{metrics.get('cpu_used', 0)}m",
                "mem_capacity": f"{mem_cap}Mi",
                "mem_used": f"{metrics.get('mem_used', 0)}Mi",
                "os": n.status.node_info.os_image if n.status.node_info else None,
                "kubelet_version": n.status.node_info.kubelet_version if n.status.node_info else None,
            })
        return results

    # ── Namespace ────────────────────────────────────

    async def list_namespaces(self) -> list[str]:
        ns_list = await self.core.list_namespace()
        return [ns.metadata.name for ns in ns_list.items]

    async def ensure_namespace(self, name: str, extra_labels: dict[str, str] | None = None):
        labels = {"app.kubernetes.io/managed-by": "nodeskclaw"}
        if extra_labels:
            labels.update(extra_labels)
        try:
            await self.core.read_namespace(name)
        except k8s_client.ApiException as e:
            if e.status == 404:
                body = k8s_client.V1Namespace(
                    metadata=k8s_client.V1ObjectMeta(name=name, labels=labels)
                )
                await self.core.create_namespace(body)
            else:
                raise

    # ── Deployment ───────────────────────────────────

    async def get_deployment(self, ns: str, name: str):
        return await self.apps.read_namespaced_deployment(name, ns)

    async def get_deployment_status(self, ns: str, name: str) -> dict:
        dep = await self.apps.read_namespaced_deployment_status(name, ns)
        status = dep.status
        return {
            "replicas": status.replicas or 0,
            "ready_replicas": status.ready_replicas or 0,
            "updated_replicas": status.updated_replicas or 0,
            "available_replicas": status.available_replicas or 0,
            "conditions": [
                {"type": c.type, "status": c.status, "message": c.message}
                for c in (status.conditions or [])
            ],
        }

    async def scale_deployment(self, ns: str, name: str, replicas: int):
        body = {"spec": {"replicas": replicas}}
        await self.apps.patch_namespaced_deployment_scale(name, ns, body)

    async def restart_deployment(self, ns: str, name: str):
        """Trigger rolling restart by patching annotation."""
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "nodeskclaw/restartedAt": datetime.now(timezone.utc).isoformat()
                        }
                    }
                }
            }
        }
        await self.apps.patch_namespaced_deployment(name, ns, body)

    async def update_deployment_image(self, ns: str, name: str, image: str):
        body = {"spec": {"template": {"spec": {"containers": [{"name": name, "image": image}]}}}}
        await self.apps.patch_namespaced_deployment(name, ns, body)

    # ── Pod ──────────────────────────────────────────

    async def list_pods(self, ns: str, label_selector: str = "") -> list[dict]:
        resp = await self.core.list_namespaced_pod(ns, label_selector=label_selector)
        results = []
        for pod in resp.items:
            containers = []
            for cs in pod.status.container_statuses or []:
                containers.append(
                    {
                        "name": cs.name,
                        "ready": cs.ready,
                        "restart_count": cs.restart_count,
                        "state": _container_state(cs.state),
                    }
                )
            results.append(
                {
                    "name": pod.metadata.name,
                    "phase": pod.status.phase,
                    "node": pod.spec.node_name,
                    "ip": pod.status.pod_ip,
                    "containers": containers,
                    "created_at": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None,
                }
            )
        return results

    async def get_pod_logs(
        self, ns: str, pod: str, container: str | None = None, tail_lines: int = 200
    ) -> str:
        return await self.core.read_namespaced_pod_log(
            pod, ns, container=container, tail_lines=tail_lines
        )

    async def stream_pod_logs(
        self, ns: str, pod: str, container: str | None = None, tail_lines: int = 50,
        since_seconds: int | None = None, since_time: str | None = None,
    ) -> AsyncIterator[str]:
        """Yield log lines as async iterator, with optional time range."""
        kwargs: dict = {
            "container": container,
            "follow": True,
            "_preload_content": False,
        }
        if since_seconds:
            kwargs["since_seconds"] = since_seconds
        elif since_time:
            # K8s API accepts RFC3339 timestamp
            kwargs["since_time"] = since_time
        else:
            kwargs["tail_lines"] = tail_lines

        resp = await self.core.read_namespaced_pod_log(pod, ns, **kwargs)
        async for line in resp.content:
            yield line.decode("utf-8", errors="replace").rstrip("\n")

    # ── Exec ──────────────────────────────────────────

    async def exec_in_pod(
        self, ns: str, pod: str, command: list[str], container: str | None = None
    ) -> str:
        """Execute a command in a pod and return stdout."""
        async with _ExecWsApiClient(self._api.configuration) as ws_api:
            core_ws = k8s_client.CoreV1Api(api_client=ws_api)
            resp = await core_ws.connect_get_namespaced_pod_exec(
                pod, ns,
                command=command,
                container=container,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
            )
        return resp.strip() if resp else ""

    async def exec_in_pod_binary(
        self, ns: str, pod: str, command: list[str], container: str | None = None
    ) -> str:
        """Execute a command and return raw stdout without stderr mixing."""
        async with _ExecWsApiClient(self._api.configuration) as ws_api:
            core_ws = k8s_client.CoreV1Api(api_client=ws_api)
            resp = await core_ws.connect_get_namespaced_pod_exec(
                pod, ns,
                command=command,
                container=container,
                stderr=False,
                stdin=False,
                stdout=True,
                tty=False,
            )
        return resp or ""

    # ── Watch ────────────────────────────────────────

    async def watch_pods(self, ns: str, label_selector: str = "", timeout_seconds: int = 1800) -> AsyncIterator[dict]:
        w = watch.Watch()
        async for event in w.stream(
            self.core.list_namespaced_pod, ns, label_selector=label_selector, timeout_seconds=timeout_seconds
        ):
            yield {"type": event["type"], "pod": event["object"].metadata.name, "phase": event["object"].status.phase}

    async def watch_events(self, ns: str, timeout_seconds: int = 1800) -> AsyncIterator[dict]:
        w = watch.Watch()
        async for event in w.stream(
            self.core.list_namespaced_event, ns, timeout_seconds=timeout_seconds
        ):
            obj = event["object"]
            yield {
                "type": event["type"],
                "reason": obj.reason,
                "message": obj.message,
                "involved": obj.involved_object.name if obj.involved_object else None,
                "count": obj.count,
                "last_timestamp": obj.last_timestamp.isoformat() if obj.last_timestamp else None,
            }

    # ── Metrics ──────────────────────────────────────

    async def list_pod_metrics(self, ns: str) -> list[dict]:
        try:
            data = await self.custom.list_namespaced_custom_object(
                "metrics.k8s.io", "v1beta1", ns, "pods"
            )
            results = []
            for item in data.get("items", []):
                containers = item.get("containers", [])
                results.append(
                    {
                        "name": item["metadata"]["name"],
                        "cpu": sum(_parse_cpu(c.get("usage", {}).get("cpu", "0")) for c in containers),
                        "memory": sum(
                            _parse_memory(c.get("usage", {}).get("memory", "0")) for c in containers
                        ),
                    }
                )
            return results
        except Exception:
            return []

    # ── PVC / PV ─────────────────────────────────────

    async def read_pvc(self, ns: str, name: str):
        return await self.core.read_namespaced_persistent_volume_claim(name, ns)

    async def read_pv(self, name: str):
        return await self.core.read_persistent_volume(name)

    # ── Service / Ingress ────────────────────────────

    async def get_service(self, ns: str, name: str):
        return await self.core.read_namespaced_service(name, ns)

    async def get_ingress(self, ns: str, name: str):
        return await self.networking.read_namespaced_ingress(name, ns)

    # ── Helpers ──────────────────────────────────────

    async def create_or_skip(self, create_fn, *args, **kwargs):
        """Create a resource; skip if already exists (409)."""
        try:
            return await create_fn(*args, **kwargs)
        except k8s_client.ApiException as e:
            if e.status == 409:
                logger.info("Resource already exists, skipping.")
            else:
                raise

    async def apply(self, create_fn, patch_fn, ns: str, name: str, body):
        """Create or update (idempotent)."""
        try:
            return await create_fn(ns, body)
        except k8s_client.ApiException as e:
            if e.status == 409:
                return await patch_fn(name, ns, body)
            raise


# ── Utility functions ────────────────────────────────

def _parse_cpu(value: str) -> int:
    """Parse CPU to millicores."""
    if value.endswith("m"):
        return int(value[:-1])
    if value.endswith("n"):
        return int(value[:-1]) // 1_000_000
    try:
        return int(float(value) * 1000)
    except ValueError:
        return 0


def _parse_memory(value: str) -> int:
    """Parse Kubernetes resource.Quantity memory string to MiB.
    Handles: m (milli-bytes), Ki/Mi/Gi/Ti (binary), K/M/G/T (SI), plain bytes."""
    value = str(value).strip()
    if not value or value == "0":
        return 0
    # Binary units (IEC): Ki, Mi, Gi, Ti — must check 2-char suffixes first
    if value.endswith("Ki"):
        return int(value[:-2]) // 1024
    if value.endswith("Mi"):
        return int(value[:-2])
    if value.endswith("Gi"):
        return int(float(value[:-2]) * 1024)
    if value.endswith("Ti"):
        return int(float(value[:-2]) * 1024 * 1024)
    # "m" suffix = milli-bytes (Kubernetes Quantity), e.g. "61215641108480m"
    if value.endswith("m"):
        try:
            milli_bytes = int(value[:-1])
            return milli_bytes // 1000 // (1024 * 1024)
        except ValueError:
            pass
    # SI units: K/k, M, G, T (decimal)
    if value.endswith("G"):
        return int(float(value[:-1]) * 1000_000_000 / (1024 * 1024))
    if value.endswith("M"):
        return int(float(value[:-1]) * 1000_000 / (1024 * 1024))
    if value.endswith("K") or value.endswith("k"):
        return int(float(value[:-1]) * 1000 / (1024 * 1024))
    if value.endswith("T"):
        return int(float(value[:-1]) * 1000_000_000_000 / (1024 * 1024))
    # Plain bytes (may include float / exponential notation)
    try:
        return int(float(value)) // (1024 * 1024)
    except (ValueError, OverflowError):
        logger.warning("Failed to parse memory value: %s", value)
        return 0


def _container_state(state) -> str:
    if state is None:
        return "unknown"
    if state.running:
        return "running"
    if state.waiting:
        return state.waiting.reason or "waiting"
    if state.terminated:
        return state.terminated.reason or "terminated"
    return "unknown"
