"""Organization management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import hooks
from app.core.deps import (
    get_current_org,
    get_db,
    require_feature,
    require_org_admin,
    require_super_admin_dep,
)
from app.core.security import get_current_user
from app.models.base import not_deleted
from app.models.org_membership import OrgMembership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.organization import (
    AddMemberRequest,
    MemberInfo,
    OAuthOrgSetupRequest,
    OrgCreate,
    OrgInfo,
    OrgNameUpdate,
    OrgUpdate,
    ResetPasswordResponse,
    UpdateMemberRoleRequest,
)
from app.services import auth_service, org_service

router = APIRouter()


# ── 组织 CRUD（超管） ────────────────────────────────────

@router.get("", response_model=ApiResponse[list[OrgInfo]],
            dependencies=[Depends(require_feature("platform_admin"))])
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin_dep),
):
    """列出所有组织（超管）。"""
    data = await org_service.list_orgs(db)
    return ApiResponse(data=data)


@router.post("", response_model=ApiResponse[OrgInfo],
             dependencies=[Depends(require_feature("platform_admin"))])
async def create_organization(
    body: OrgCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin_dep),
):
    """创建组织（超管）。"""
    data = await org_service.create_org(body, admin, db)
    await hooks.emit("operation_audit", action="org.created", target_type="organization", target_id=data.id, actor_id=admin.id)
    return ApiResponse(data=data)


@router.get("/my", response_model=ApiResponse[list[OrgInfo]],
            dependencies=[Depends(require_feature("multi_org"))])
async def list_my_organizations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出当前用户所属的所有组织。"""
    data = await org_service.list_user_orgs(current_user, db)
    return ApiResponse(data=data)


async def _enrich_org_info(org: Organization, db: AsyncSession) -> OrgInfo:
    """补充 cluster_name 和 member_count。"""
    cluster_name = None
    if org.cluster_id:
        from app.models.cluster import Cluster
        result = await db.execute(
            select(Cluster.name).where(Cluster.id == org.cluster_id, not_deleted(Cluster))
        )
        cluster_name = result.scalar_one_or_none()

    member_count_result = await db.execute(
        select(func.count(OrgMembership.id)).where(
            OrgMembership.org_id == org.id, not_deleted(OrgMembership)
        )
    )
    info = OrgInfo.model_validate(org)
    info.cluster_name = cluster_name
    info.member_count = member_count_result.scalar_one() or 0
    return info


# ── 当前组织（CE/EE 通用，不受 feature gate 限制） ──────────

@router.get("/current", response_model=ApiResponse[OrgInfo])
async def get_current_organization(
    db: AsyncSession = Depends(get_db),
    org_ctx: tuple = Depends(get_current_org),
):
    """获取当前用户所在组织的详情。"""
    _user, org = org_ctx
    data = await _enrich_org_info(org, db)
    return ApiResponse(data=data)


@router.put("/current/name", response_model=ApiResponse[OrgInfo])
async def update_current_org_name(
    body: OrgNameUpdate,
    db: AsyncSession = Depends(get_db),
    org_ctx: tuple = Depends(require_org_admin),
):
    """组织管理员修改当前组织名称。"""
    _user, org = org_ctx
    await org_service.update_org(org.id, OrgUpdate(name=body.name), db)
    await db.refresh(org)
    data = await _enrich_org_info(org, db)
    return ApiResponse(data=data)


@router.post("/switch/{org_id}", response_model=ApiResponse[OrgInfo],
             dependencies=[Depends(require_feature("multi_org"))])
async def switch_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """切换当前组织。"""
    data = await org_service.switch_org(current_user, org_id, db)
    return ApiResponse(data=data)


@router.get("/{org_id}", response_model=ApiResponse[OrgInfo],
            dependencies=[Depends(require_feature("platform_admin"))])
async def get_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin_dep),
):
    """组织详情（超管）。"""
    org = await org_service.get_org(org_id, db)
    return ApiResponse(data=OrgInfo.model_validate(org))


@router.put("/{org_id}", response_model=ApiResponse[OrgInfo],
            dependencies=[Depends(require_feature("platform_admin"))])
async def update_organization(
    org_id: str,
    body: OrgUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin_dep),
):
    """更新组织（超管）。"""
    data = await org_service.update_org(org_id, body, db)
    await hooks.emit("operation_audit", action="org.updated", target_type="organization", target_id=org_id, actor_id=_admin.id)
    return ApiResponse(data=data)


@router.delete("/{org_id}", response_model=ApiResponse,
               dependencies=[Depends(require_feature("platform_admin"))])
async def delete_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin_dep),
):
    """删除组织（超管）。"""
    await org_service.delete_org(org_id, db)
    await hooks.emit("operation_audit", action="org.deleted", target_type="organization", target_id=org_id, actor_id=_admin.id)
    return ApiResponse(message="组织已删除")


# ── OAuth 自助开通 ─────────────────────────────────────────

@router.post("/oauth-setup", response_model=ApiResponse[OrgInfo])
async def oauth_org_setup(
    body: OAuthOrgSetupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """OAuth 登录后首次开通组织：创建组织并绑定 OAuth 租户。"""
    data = await org_service.oauth_org_setup(current_user, body, db)
    return ApiResponse(data=data)


@router.post("/feishu-setup", response_model=ApiResponse[OrgInfo])
async def feishu_org_setup(
    body: OAuthOrgSetupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """飞书开通组织（向后兼容别名）。"""
    if not body.provider:
        body.provider = "feishu"
    data = await org_service.oauth_org_setup(current_user, body, db)
    return ApiResponse(data=data)


# ── 成员管理 ─────────────────────────────────────────────

@router.get("/{org_id}/members", response_model=ApiResponse[list[MemberInfo]],
            dependencies=[Depends(require_feature("multi_org"))])
async def list_members(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _org_ctx: tuple = Depends(require_org_admin),
):
    """列出组织成员（组织管理员+）。"""
    data = await org_service.list_members(org_id, db)
    return ApiResponse(data=data)


@router.post("/{org_id}/members", response_model=ApiResponse[MemberInfo],
             dependencies=[Depends(require_feature("multi_org"))])
async def add_member(
    org_id: str,
    body: AddMemberRequest,
    db: AsyncSession = Depends(get_db),
    _org_ctx: tuple = Depends(require_org_admin),
):
    """添加成员（组织管理员+）。"""
    data = await org_service.add_member(org_id, body.user_id, body.role, db)
    await hooks.emit("operation_audit", action="org.member_added", target_type="org_membership", target_id=data.id, actor_id=_org_ctx[0].id, org_id=org_id)
    return ApiResponse(data=data)


@router.put("/{org_id}/members/{membership_id}", response_model=ApiResponse[MemberInfo],
            dependencies=[Depends(require_feature("multi_org"))])
async def update_member_role(
    org_id: str,
    membership_id: str,
    body: UpdateMemberRoleRequest,
    db: AsyncSession = Depends(get_db),
    _org_ctx: tuple = Depends(require_org_admin),
):
    """修改成员角色（组织管理员+）。"""
    data = await org_service.update_member_role(org_id, membership_id, body.role, db)
    await hooks.emit("operation_audit", action="org.member_role_updated", target_type="org_membership", target_id=membership_id, actor_id=_org_ctx[0].id, org_id=org_id)
    return ApiResponse(data=data)


@router.delete("/{org_id}/members/{membership_id}", response_model=ApiResponse,
               dependencies=[Depends(require_feature("multi_org"))])
async def remove_member(
    org_id: str,
    membership_id: str,
    db: AsyncSession = Depends(get_db),
    _org_ctx: tuple = Depends(require_org_admin),
):
    """移除成员（组织管理员+）。"""
    await org_service.remove_member(org_id, membership_id, db)
    await hooks.emit("operation_audit", action="org.member_removed", target_type="org_membership", target_id=membership_id, actor_id=_org_ctx[0].id, org_id=org_id)
    return ApiResponse(message="成员已移除")


@router.post("/{org_id}/members/{user_id}/reset-password", response_model=ApiResponse[ResetPasswordResponse],
             dependencies=[Depends(require_feature("multi_org"))])
async def reset_member_password(
    org_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _org_ctx: tuple = Depends(require_org_admin),
):
    """重置成员密码（组织管理员，仅限 member 角色）。"""
    from app.models.org_membership import OrgMembership

    current_user = _org_ctx[0]

    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": 40326,
                "message_key": "errors.org.cannot_reset_own_password",
                "message": "不能重置自己的密码，请到设置页修改",
            },
        )

    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == user_id,
            OrgMembership.org_id == org_id,
            OrgMembership.deleted_at.is_(None),
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": 40402,
                "message_key": "errors.org.member_not_found",
                "message": "该用户不是当前组织的成员",
            },
        )

    if membership.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": 40327,
                "message_key": "errors.org.cannot_reset_admin_password",
                "message": "不能重置其他管理员的密码",
            },
        )

    plain = await auth_service.admin_reset_password(user_id, db)
    await hooks.emit("operation_audit", action="org.member_password_reset", target_type="org_membership", target_id=user_id, actor_id=current_user.id, org_id=org_id)
    return ApiResponse(data=ResetPasswordResponse(password=plain))


# ── 组织级 AKR 汇总 ────────────────────────────────────

@router.get("/{org_id}/akr-summary",
            dependencies=[Depends(require_feature("akr_management"))])
async def org_akr_summary(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _org_ctx: tuple = Depends(require_org_admin),
):
    """Aggregate AKR data across all workspaces in the org."""
    from app.models.workspace import Workspace
    from app.models.workspace_objective import WorkspaceObjective
    from app.models.workspace_task import WorkspaceTask

    ws_rows = (await db.execute(
        select(Workspace.id, Workspace.name).where(
            Workspace.org_id == org_id,
            Workspace.deleted_at.is_(None),
        )
    )).all()

    ws_ids = [r[0] for r in ws_rows]
    ws_names = {r[0]: r[1] for r in ws_rows}

    if not ws_ids:
        return ApiResponse(data={"workspaces": []})

    objectives = (await db.execute(
        select(WorkspaceObjective).where(
            WorkspaceObjective.workspace_id.in_(ws_ids),
            WorkspaceObjective.deleted_at.is_(None),
        )
    )).scalars().all()

    tasks = (await db.execute(
        select(WorkspaceTask).where(
            WorkspaceTask.workspace_id.in_(ws_ids),
            WorkspaceTask.deleted_at.is_(None),
        )
    )).scalars().all()

    workspaces = []
    for ws_id in ws_ids:
        ws_objs = [o for o in objectives if o.workspace_id == ws_id]
        ws_tasks = [t for t in tasks if t.workspace_id == ws_id]
        total_t = len(ws_tasks)
        done_t = sum(1 for t in ws_tasks if t.status in ("done", "archived"))
        total_value = sum(t.actual_value or 0 for t in ws_tasks if t.status in ("done", "archived"))
        total_tokens = sum(t.token_cost or 0 for t in ws_tasks)
        roi = total_value / total_tokens * 1000 if total_tokens > 0 else 0.0

        obj_summaries = []
        for o in ws_objs:
            if o.obj_type == "objective":
                kr_count = sum(1 for x in ws_objs if x.parent_id == o.id)
                obj_summaries.append({
                    "id": o.id, "title": o.title, "progress": o.progress,
                    "kr_count": kr_count,
                })

        workspaces.append({
            "workspace_id": ws_id,
            "workspace_name": ws_names.get(ws_id, ""),
            "objectives": obj_summaries,
            "total_tasks": total_t,
            "completed_tasks": done_t,
            "completion_rate": round(done_t / total_t, 4) if total_t > 0 else 0.0,
            "total_value": round(total_value, 2),
            "total_tokens": total_tokens,
            "roi_per_1k_tokens": round(roi, 4),
        })

    return ApiResponse(data={"workspaces": workspaces})
