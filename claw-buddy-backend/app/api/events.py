"""K8s events SSE streaming endpoints."""

import json
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.exceptions import NotFoundError
from app.core.security import get_current_user
from app.models.cluster import Cluster
from app.models.user import User
from app.services.k8s.client_manager import k8s_manager
from app.services.k8s.k8s_client import K8sClient

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/stream")
async def events_stream(
    cluster_id: str = Query(..., description="集群 ID"),
    namespace: str = Query("", description="命名空间，留空则监听所有"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """SSE 流: 实时推送 K8s 事件。"""
    result = await db.execute(select(Cluster).where(Cluster.id == cluster_id))
    cluster = result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")

    api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)

    async def generate():
        k8s = K8sClient(api_client)
        try:
            if namespace:
                event_gen = k8s.watch_events(namespace)
            else:
                event_gen = _watch_all_events(k8s)

            async for event in event_gen:
                data = json.dumps(event, default=str)
                yield f"event: k8s_event\ndata: {data}\n\n"
        except Exception as e:
            logger.warning("事件流中断: %s", e)
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


async def _watch_all_events(k8s: K8sClient):
    """Watch events across all namespaces."""
    from kubernetes_asyncio import watch

    w = watch.Watch()
    async for event in w.stream(
        k8s.core.list_event_for_all_namespaces, timeout_seconds=0
    ):
        obj = event["object"]
        yield {
            "type": event["type"],
            "event_type": obj.type or "Normal",
            "reason": obj.reason,
            "message": obj.message,
            "involved": obj.involved_object.name if obj.involved_object else None,
            "involved_kind": obj.involved_object.kind if obj.involved_object else None,
            "namespace": obj.metadata.namespace,
            "count": obj.count,
            "last_timestamp": obj.last_timestamp.isoformat() if obj.last_timestamp else None,
            "first_timestamp": obj.event_time.isoformat() if obj.event_time else (
                obj.first_timestamp.isoformat() if obj.first_timestamp else None
            ),
        }
