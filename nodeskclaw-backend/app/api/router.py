"""Central router that aggregates all API sub-routers."""

from fastapi import APIRouter, Depends

from app.api.auth import router as auth_router
from app.api.genes import router as gene_router
from app.api.clusters import router as cluster_router
from app.api.deploy import router as deploy_router
from app.api.events import router as events_router
from app.api.instances import (
    instance_read_router,
    instance_write_router,
)
from app.api.llm_keys import router as llm_keys_router
from app.api.organizations import router as org_router
from app.api.org_settings import router as org_settings_router
from app.api.registry import router as registry_router
from app.api.settings import router as settings_router
from app.api.storage import router as storage_router
from app.api.corridors import router as corridor_router
from app.api.channel_configs import router as channel_config_router
from app.api.observability import router as observability_router
from app.api.runtime_admin import router as runtime_admin_router
from app.api.mcp import router as mcp_router
from app.api.trust import router as trust_router
from app.api.webhooks import router as webhook_router
from app.api.workspaces import router as workspace_router
from app.api.templates import router as template_router
from app.api.instance_templates import router as instance_template_router
from app.core.deps import require_ce_edition, require_org_admin, require_org_role
from app.core.feature_gate import feature_gate
from app.core.config import settings

from app.api.security_ws import router as security_ws_router
from app.api.engines import router as engine_router
from app.api.invitations import invite_router, invite_public_router
from app.api.portal.instances import router as portal_instance_router
from app.api.portal.instance_members import router as portal_instance_members_router
from app.api.portal.deploy import router as portal_deploy_router
from app.api.portal.channel_configs import router as portal_channel_config_router
from app.api.portal.mcp import router as portal_mcp_router
from app.api.portal.instance_files import router as portal_instance_files_router

# ── Portal 公共 API（/api/v1）──────────────────────────────
# Portal 使用 portal/ 下的独立路由，内置实例级权限检查。

api_router = APIRouter()


@api_router.get("/health", tags=["系统"])
async def health_check():
    """NoDeskClaw backend health probe."""
    return {"status": "ok"}


@api_router.get("/system/info", tags=["系统"])
async def system_info():
    """暴露 edition 和启用的 feature 列表，供前端初始化使用。"""
    return {
        "edition": feature_gate.edition,
        "version": settings.APP_VERSION,
        "features": feature_gate.all_features(),
    }


@api_router.get("/system/capabilities", tags=["系统"])
async def system_capabilities():
    """暴露系统能力状态（如文件上传是否可用），供前端控制 UI 状态。"""
    from app.services import storage_service
    return {
        "file_upload_enabled": storage_service.is_configured(),
    }


api_router.include_router(auth_router, prefix="/auth", tags=["认证"])
api_router.include_router(org_router, prefix="/orgs", tags=["组织"])
api_router.include_router(org_settings_router, prefix="/orgs", tags=["组织设置"])
api_router.include_router(cluster_router, prefix="/clusters", tags=["集群"])
api_router.include_router(portal_deploy_router, prefix="/deploy", tags=["部署"])
api_router.include_router(events_router, prefix="/events", tags=["事件"])
api_router.include_router(portal_instance_router, prefix="/instances", tags=["实例"])
api_router.include_router(portal_instance_members_router, prefix="/instances", tags=["实例成员"])
api_router.include_router(portal_channel_config_router, prefix="/instances", tags=["Channel 配置"])
api_router.include_router(portal_mcp_router, prefix="/instances", tags=["MCP"])
api_router.include_router(portal_instance_files_router, prefix="/instances", tags=["实例文件"])
api_router.include_router(llm_keys_router, tags=["LLM Key 管理"])
api_router.include_router(registry_router, prefix="/registry", tags=["镜像仓库"])
api_router.include_router(settings_router, prefix="/settings", tags=["系统配置"],
    dependencies=[Depends(require_ce_edition), Depends(require_org_admin)])
api_router.include_router(storage_router, prefix="/storage-classes", tags=["存储"])
api_router.include_router(workspace_router, prefix="/workspaces", tags=["赛博办公室"])
api_router.include_router(corridor_router, prefix="/workspaces", tags=["过道系统"])
api_router.include_router(observability_router, prefix="/workspaces", tags=["可观测性"])
api_router.include_router(trust_router, prefix="/workspaces", tags=["渐进式信任"])
api_router.include_router(template_router, prefix="/workspaces", tags=["办公室模板"])
api_router.include_router(instance_template_router, tags=["AI 员工模板"])
api_router.include_router(gene_router, tags=["基因进化"])
api_router.include_router(engine_router, prefix="/engines", tags=["工作引擎"])
api_router.include_router(invite_router, prefix="/orgs", tags=["邀请"])
api_router.include_router(invite_public_router, prefix="/invite", tags=["邀请（公开）"])
api_router.include_router(security_ws_router, tags=["安全评估"])

# ── 管理平台 Admin API（/api/v1/admin）─────────────────────
# Admin 使用原有路由模块，通过 dependencies 注入角色检查。

admin_router = APIRouter()

# 基础路由（无额外角色限制）
admin_router.include_router(auth_router, prefix="/auth", tags=["Admin - 认证"])
admin_router.include_router(org_router, prefix="/orgs", tags=["Admin - 组织"])
admin_router.include_router(workspace_router, prefix="/workspaces", tags=["Admin - 赛博办公室"])
admin_router.include_router(corridor_router, prefix="/workspaces", tags=["Admin - 过道系统"])
admin_router.include_router(observability_router, prefix="/workspaces", tags=["Admin - 可观测性"])
admin_router.include_router(trust_router, prefix="/workspaces", tags=["Admin - 渐进式信任"])
admin_router.include_router(template_router, prefix="/workspaces", tags=["Admin - 办公室模板"])
admin_router.include_router(channel_config_router, prefix="/instances", tags=["Admin - Channel 配置"])
admin_router.include_router(mcp_router, prefix="/instances", tags=["Admin - MCP"])

# member 级别（只读查看）
admin_router.include_router(instance_read_router, prefix="/instances",
    tags=["Admin - 实例(读)"],
    dependencies=[Depends(require_org_role("member"))])
admin_router.include_router(events_router, prefix="/events",
    tags=["Admin - 事件"],
    dependencies=[Depends(require_org_role("member"))])
admin_router.include_router(storage_router, prefix="/storage-classes",
    tags=["Admin - 存储"],
    dependencies=[Depends(require_org_role("member"))])

# operator 级别（实例操作 + 部署）
admin_router.include_router(instance_write_router, prefix="/instances",
    tags=["Admin - 实例(写)"],
    dependencies=[Depends(require_org_role("operator"))])
admin_router.include_router(deploy_router, prefix="/deploy",
    tags=["Admin - 部署"],
    dependencies=[Depends(require_org_role("operator"))])

# admin 级别（集群、配置、基因、密钥等）
admin_router.include_router(cluster_router, prefix="/clusters",
    tags=["Admin - 集群"],
    dependencies=[Depends(require_org_role("admin"))])
admin_router.include_router(settings_router, prefix="/settings",
    tags=["Admin - 系统配置"],
    dependencies=[Depends(require_org_role("admin"))])
admin_router.include_router(gene_router,
    tags=["Admin - 基因进化"],
    dependencies=[Depends(require_org_role("admin"))])
admin_router.include_router(llm_keys_router,
    tags=["Admin - LLM Key 管理"],
    dependencies=[Depends(require_org_role("admin"))])
admin_router.include_router(registry_router, prefix="/registry",
    tags=["Admin - 镜像仓库"],
    dependencies=[Depends(require_org_role("admin"))])
admin_router.include_router(runtime_admin_router, prefix="/runtime",
    tags=["Admin - 运行时平台"],
    dependencies=[Depends(require_org_role("admin"))])
