"""Central router that aggregates all API sub-routers."""

from fastapi import APIRouter, Depends, Request

from app.api.audit import router as audit_router
from app.api.agent_file_grants import router as agent_file_grants_router
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
from app.api.spec_presets import router as spec_presets_router
from app.api.storage import router as storage_router
from app.api.conversations import router as conversation_router
from app.api.corridors import router as corridor_router
from app.api.channel_configs import router as channel_config_router
from app.api.observability import router as observability_router
from app.api.runtime_admin import router as runtime_admin_router
from app.api.mcp import router as mcp_router
from app.api.trust import router as trust_router
from app.api.uploads import router as uploads_router
from app.api.webhooks import router as webhook_router
from app.api.blackboard import router as blackboard_router
from app.api.performance import router as performance_router
from app.api.workspaces import router as workspace_router
from app.api.templates import router as template_router
from app.api.workspace_deploys import router as workspace_deploys_router
from app.api.instance_templates import router as instance_template_router
from app.core.deps import get_db, require_ce_edition, require_org_admin, require_org_role
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.feature_gate import feature_gate
from app.core.config import settings

from app.api.security_ws import router as security_ws_router
from app.api.tunnel import router as tunnel_router
from app.api.engines import router as engine_router
from app.api.engine_versions import (
    engine_version_read_router,
    engine_version_write_router,
)
from app.api.image_builds import image_build_read_router, image_build_write_router
from app.api.invitations import invite_router, invite_public_router
from app.api.portal.instances import router as portal_instance_router
from app.api.portal.instance_members import router as portal_instance_members_router
from app.api.portal.deploy import router as portal_deploy_router
from app.api.portal.channel_configs import router as portal_channel_config_router
from app.api.portal.mcp import router as portal_mcp_router
from app.api.portal.instance_files import router as portal_instance_files_router
from app.api.portal.clusters import router as portal_cluster_router, write_router as portal_cluster_write_router
from app.api.portal.events import router as portal_events_router

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
async def system_capabilities(db=Depends(get_db)):
    """暴露系统能力状态（如文件上传是否可用），供前端控制 UI 状态。"""
    from app.services.upload_policy_service import build_upload_policy
    upload_policy = await build_upload_policy(db)
    return {
        "file_upload_enabled": upload_policy["storage_status"] == "available",
        "upload_policy": upload_policy,
    }


@api_router.get("/files/local/{file_key:path}", tags=["文件"])
async def serve_local_file(file_key: str, request: Request, expires: str = "", sig: str = ""):
    """Serve a local file using HMAC-signed URL (no Bearer token required)."""
    from pathlib import Path

    from app.api.file_downloads import build_storage_download_response
    from app.services import storage_service

    if storage_service._use_s3():
        raise NotFoundError("对象存储启用时不提供本地文件服务", "errors.storage.local_file_disabled")

    if not expires or not sig:
        raise ForbiddenError("缺少签名参数", "errors.storage.signature_missing")

    if not storage_service.verify_signature(file_key, expires, sig):
        raise ForbiddenError("签名无效或已过期", "errors.storage.signature_invalid")

    file_path = storage_service._get_local_dir() / file_key
    if not file_path.is_file():
        raise NotFoundError("文件不存在", "errors.storage.file_not_found")

    return await build_storage_download_response(
        storage_key=file_key,
        filename=Path(file_key).name,
        content_type="application/octet-stream",
        range_header=request.headers.get("range"),
    )


api_router.include_router(auth_router, prefix="/auth", tags=["认证"])
api_router.include_router(agent_file_grants_router, tags=["文件授权"])
api_router.include_router(org_router, prefix="/orgs", tags=["组织"])
api_router.include_router(org_settings_router, prefix="/orgs", tags=["组织设置"])
api_router.include_router(audit_router, prefix="/orgs", tags=["操作审计"])
api_router.include_router(portal_cluster_router, prefix="/clusters", tags=["集群"])
api_router.include_router(portal_cluster_write_router, prefix="/clusters", tags=["集群"],
    dependencies=[Depends(require_ce_edition), Depends(require_org_admin)])
api_router.include_router(portal_deploy_router, prefix="/deploy", tags=["部署"])
api_router.include_router(portal_events_router, prefix="/events", tags=["事件"])
api_router.include_router(portal_instance_router, prefix="/instances", tags=["实例"])
api_router.include_router(portal_instance_members_router, prefix="/instances", tags=["实例成员"])
api_router.include_router(portal_channel_config_router, prefix="/instances", tags=["Channel 配置"])
api_router.include_router(portal_mcp_router, prefix="/instances", tags=["MCP"])
api_router.include_router(portal_instance_files_router, prefix="/instances", tags=["实例文件"])
api_router.include_router(llm_keys_router, tags=["LLM Key 管理"])
api_router.include_router(performance_router, tags=["绩效"])
api_router.include_router(registry_router, prefix="/registry", tags=["镜像仓库"])
api_router.include_router(settings_router, prefix="/settings", tags=["系统配置"],
    dependencies=[Depends(require_ce_edition), Depends(require_org_admin)])
api_router.include_router(uploads_router, tags=["文件上传"])
api_router.include_router(spec_presets_router, prefix="/spec-presets", tags=["规格预设"])
api_router.include_router(storage_router, prefix="/storage-classes", tags=["存储"])
api_router.include_router(template_router, prefix="/workspaces", tags=["办公室模板"])
api_router.include_router(workspace_deploys_router, prefix="/workspaces", tags=["办公室模板部署"])
api_router.include_router(workspace_router, prefix="/workspaces", tags=["赛博办公室"])
api_router.include_router(blackboard_router, prefix="/workspaces", tags=["黑板讨论区"])
api_router.include_router(conversation_router, prefix="/workspaces", tags=["群聊"])
api_router.include_router(corridor_router, prefix="/workspaces", tags=["过道系统"])
api_router.include_router(observability_router, prefix="/workspaces", tags=["可观测性"])
api_router.include_router(trust_router, prefix="/workspaces", tags=["渐进式信任"])
api_router.include_router(instance_template_router, tags=["AI 员工模板"])
api_router.include_router(gene_router, tags=["基因进化"])
api_router.include_router(engine_router, prefix="/engines", tags=["工作引擎"])
api_router.include_router(engine_version_read_router, prefix="/engine-versions", tags=["引擎版本"])
api_router.include_router(engine_version_write_router, prefix="/engine-versions", tags=["引擎版本"],
    dependencies=[Depends(require_ce_edition), Depends(require_org_admin)])
api_router.include_router(image_build_read_router, prefix="/image-builds", tags=["镜像构建"])
api_router.include_router(image_build_write_router, prefix="/image-builds", tags=["镜像构建"],
    dependencies=[Depends(require_ce_edition), Depends(require_org_admin)])
api_router.include_router(invite_router, prefix="/orgs", tags=["邀请"])
api_router.include_router(invite_public_router, prefix="/invite", tags=["邀请（公开）"])
api_router.include_router(security_ws_router, tags=["安全评估"])
api_router.include_router(tunnel_router, tags=["Agent Tunnel"])

# ── 管理平台 Admin API（/api/v1/admin）─────────────────────
# Admin 使用原有路由模块，通过 dependencies 注入角色检查。

admin_router = APIRouter()

# 基础路由（无额外角色限制）
admin_router.include_router(auth_router, prefix="/auth", tags=["Admin - 认证"])
admin_router.include_router(org_router, prefix="/orgs", tags=["Admin - 组织"])
admin_router.include_router(template_router, prefix="/workspaces", tags=["Admin - 办公室模板"])
admin_router.include_router(workspace_deploys_router, prefix="/workspaces", tags=["Admin - 办公室模板部署"])
admin_router.include_router(workspace_router, prefix="/workspaces", tags=["Admin - 赛博办公室"])
admin_router.include_router(blackboard_router, prefix="/workspaces", tags=["Admin - 黑板讨论区"])
admin_router.include_router(conversation_router, prefix="/workspaces", tags=["Admin - 群聊"])
admin_router.include_router(corridor_router, prefix="/workspaces", tags=["Admin - 过道系统"])
admin_router.include_router(observability_router, prefix="/workspaces", tags=["Admin - 可观测性"])
admin_router.include_router(trust_router, prefix="/workspaces", tags=["Admin - 渐进式信任"])
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
admin_router.include_router(uploads_router,
    tags=["Admin - 文件上传"])
admin_router.include_router(spec_presets_router, prefix="/spec-presets",
    tags=["Admin - 规格预设"])
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
admin_router.include_router(engine_version_read_router, prefix="/engine-versions",
    tags=["Admin - 引擎版本(读)"],
    dependencies=[Depends(require_org_role("member"))])
admin_router.include_router(engine_version_write_router, prefix="/engine-versions",
    tags=["Admin - 引擎版本(写)"],
    dependencies=[Depends(require_org_role("admin"))])
admin_router.include_router(image_build_read_router, prefix="/image-builds",
    tags=["Admin - 镜像构建(读)"],
    dependencies=[Depends(require_org_role("member"))])
admin_router.include_router(image_build_write_router, prefix="/image-builds",
    tags=["Admin - 镜像构建(写)"],
    dependencies=[Depends(require_org_role("admin"))])
admin_router.include_router(tunnel_router, tags=["Admin - Agent Tunnel"],
    dependencies=[Depends(require_org_role("admin"))])
