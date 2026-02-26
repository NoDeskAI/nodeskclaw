"""Central router that aggregates all API sub-routers."""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.billing import router as billing_router
from app.api.corridors import router as corridor_router
from app.api.genes import router as gene_router
from app.api.clusters import router as cluster_router
from app.api.deploy import router as deploy_router
from app.api.events import router as events_router
from app.api.instances import router as instance_router
from app.api.llm_keys import router as llm_keys_router
from app.api.organizations import router as org_router
from app.api.registry import router as registry_router
from app.api.settings import router as settings_router
from app.api.storage import router as storage_router
from app.api.workspaces import router as workspace_router

api_router = APIRouter()


@api_router.get("/health", tags=["系统"])
async def health_check():
    """ClawBuddy backend health probe."""
    return {"status": "ok"}


api_router.include_router(auth_router, prefix="/auth", tags=["认证"])
api_router.include_router(org_router, prefix="/orgs", tags=["组织"])
api_router.include_router(billing_router, prefix="/billing", tags=["计费"])
api_router.include_router(cluster_router, prefix="/clusters", tags=["集群"])
api_router.include_router(deploy_router, prefix="/deploy", tags=["部署"])
api_router.include_router(events_router, prefix="/events", tags=["事件"])
api_router.include_router(instance_router, prefix="/instances", tags=["实例"])
api_router.include_router(llm_keys_router, tags=["LLM Key 管理"])
api_router.include_router(registry_router, prefix="/registry", tags=["镜像仓库"])
api_router.include_router(settings_router, prefix="/settings", tags=["系统配置"])
api_router.include_router(storage_router, prefix="/storage-classes", tags=["存储"])
api_router.include_router(workspace_router, prefix="/workspaces", tags=["工作区"])
api_router.include_router(corridor_router, prefix="/workspaces", tags=["过道系统"])
api_router.include_router(gene_router, tags=["基因进化"])
