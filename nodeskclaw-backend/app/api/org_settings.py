"""Organization settings endpoints -- required genes & SMTP configuration."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import hooks
from app.core.deps import get_db, require_feature, require_org_admin
from app.core.security import decrypt_sensitive, encrypt_sensitive
from app.models.base import not_deleted
from app.models.gene import Gene
from app.models.org_required_gene import OrgRequiredGene
from app.models.org_smtp_config import OrgSmtpConfig
from app.schemas.common import ApiResponse
from app.schemas.organization import OrgRequiredGeneAdd, OrgRequiredGeneInfo
from app.schemas.smtp import SmtpConfigCreate, SmtpConfigResponse, SmtpTestRequest

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_info(rg: OrgRequiredGene, gene: Gene) -> OrgRequiredGeneInfo:
    return OrgRequiredGeneInfo(
        id=rg.id,
        gene_id=gene.id,
        gene_name=gene.name,
        gene_slug=gene.slug,
        gene_short_description=gene.short_description,
        gene_icon=gene.icon,
        gene_category=gene.category,
    )


@router.get(
    "/{org_id}/required-genes",
    response_model=ApiResponse[list[OrgRequiredGeneInfo]],
)
async def list_required_genes(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
):
    result = await db.execute(
        select(OrgRequiredGene, Gene)
        .join(Gene, OrgRequiredGene.gene_id == Gene.id)
        .where(
            OrgRequiredGene.org_id == org_id,
            not_deleted(OrgRequiredGene),
            not_deleted(Gene),
        )
        .order_by(OrgRequiredGene.created_at)
    )
    rows = result.all()
    items = [_to_info(rg, gene) for rg, gene in rows]
    return ApiResponse(data=items)


@router.post(
    "/{org_id}/required-genes",
    response_model=ApiResponse[OrgRequiredGeneInfo],
)
async def add_required_gene(
    org_id: str,
    body: OrgRequiredGeneAdd,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
):
    gene = await db.get(Gene, body.gene_id)
    if not gene or gene.deleted_at is not None:
        raise HTTPException(404, detail={
            "error_code": 40440,
            "message_key": "errors.gene.not_found",
            "message": "基因不存在",
        })

    existing = await db.execute(
        select(OrgRequiredGene).where(
            OrgRequiredGene.org_id == org_id,
            OrgRequiredGene.gene_id == body.gene_id,
            not_deleted(OrgRequiredGene),
        ).limit(1)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, detail={
            "error_code": 40901,
            "message_key": "errors.org_settings.gene_already_required",
            "message": "该基因已在默认工作基因列表中",
        })

    rg = OrgRequiredGene(org_id=org_id, gene_id=body.gene_id)
    db.add(rg)
    await db.commit()
    await db.refresh(rg)
    await hooks.emit("operation_audit", action="org.required_gene_added", target_type="organization", target_id=org_id, actor_id=_auth[0].id, org_id=org_id, details={"gene_id": body.gene_id})
    return ApiResponse(data=_to_info(rg, gene))


@router.delete(
    "/{org_id}/required-genes/{required_gene_id}",
    response_model=ApiResponse,
)
async def remove_required_gene(
    org_id: str,
    required_gene_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
):
    result = await db.execute(
        select(OrgRequiredGene).where(
            OrgRequiredGene.id == required_gene_id,
            OrgRequiredGene.org_id == org_id,
            not_deleted(OrgRequiredGene),
        )
    )
    rg = result.scalar_one_or_none()
    if not rg:
        raise HTTPException(404, detail={
            "error_code": 40441,
            "message_key": "errors.org_settings.required_gene_not_found",
            "message": "默认工作基因记录不存在",
        })

    rg.soft_delete()
    await db.commit()
    await hooks.emit("operation_audit", action="org.required_gene_removed", target_type="organization", target_id=org_id, actor_id=_auth[0].id, org_id=org_id, details={"required_gene_id": required_gene_id})
    return ApiResponse(message="已移除")


# ── SMTP 配置 ─────────────────────────────────────────────


def _mask_password(encrypted: str) -> str:
    try:
        plain = decrypt_sensitive(encrypted)
        if len(plain) <= 3:
            return "****"
        return "****" + plain[-3:]
    except Exception:
        return "****"


def _smtp_to_response(cfg: OrgSmtpConfig) -> SmtpConfigResponse:
    return SmtpConfigResponse(
        id=cfg.id,
        smtp_host=cfg.smtp_host,
        smtp_port=cfg.smtp_port,
        smtp_username=cfg.smtp_username,
        smtp_password_masked=_mask_password(cfg.smtp_password_encrypted),
        from_email=cfg.from_email,
        from_name=cfg.from_name,
        use_tls=cfg.use_tls,
    )


@router.get(
    "/{org_id}/smtp-config",
    response_model=ApiResponse[SmtpConfigResponse | None],
    dependencies=[Depends(require_feature("org_smtp_config"))],
)
async def get_smtp_config(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
):
    result = await db.execute(
        select(OrgSmtpConfig).where(
            OrgSmtpConfig.org_id == org_id,
            not_deleted(OrgSmtpConfig),
        )
    )
    cfg = result.scalar_one_or_none()
    return ApiResponse(data=_smtp_to_response(cfg) if cfg else None)


@router.put(
    "/{org_id}/smtp-config",
    response_model=ApiResponse[SmtpConfigResponse],
    dependencies=[Depends(require_feature("org_smtp_config"))],
)
async def upsert_smtp_config(
    org_id: str,
    body: SmtpConfigCreate,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
):
    result = await db.execute(
        select(OrgSmtpConfig).where(
            OrgSmtpConfig.org_id == org_id,
            not_deleted(OrgSmtpConfig),
        )
    )
    cfg = result.scalar_one_or_none()

    encrypted_pw = encrypt_sensitive(body.smtp_password)

    if cfg:
        cfg.smtp_host = body.smtp_host
        cfg.smtp_port = body.smtp_port
        cfg.smtp_username = body.smtp_username
        cfg.smtp_password_encrypted = encrypted_pw
        cfg.from_email = body.from_email
        cfg.from_name = body.from_name
        cfg.use_tls = body.use_tls
    else:
        cfg = OrgSmtpConfig(
            org_id=org_id,
            smtp_host=body.smtp_host,
            smtp_port=body.smtp_port,
            smtp_username=body.smtp_username,
            smtp_password_encrypted=encrypted_pw,
            from_email=body.from_email,
            from_name=body.from_name,
            use_tls=body.use_tls,
        )
        db.add(cfg)

    await db.commit()
    await db.refresh(cfg)
    await hooks.emit("operation_audit", action="org.smtp_config_updated", target_type="organization", target_id=org_id, actor_id=_auth[0].id, org_id=org_id)
    return ApiResponse(data=_smtp_to_response(cfg))


@router.delete(
    "/{org_id}/smtp-config",
    response_model=ApiResponse,
    dependencies=[Depends(require_feature("org_smtp_config"))],
)
async def delete_smtp_config(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
):
    result = await db.execute(
        select(OrgSmtpConfig).where(
            OrgSmtpConfig.org_id == org_id,
            not_deleted(OrgSmtpConfig),
        )
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(404, detail={
            "error_code": 40450,
            "message_key": "errors.smtp.config_not_found",
            "message": "SMTP 配置不存在",
        })
    cfg.soft_delete()
    await db.commit()
    return ApiResponse(message="SMTP 配置已删除")


@router.post(
    "/{org_id}/smtp-config/test",
    response_model=ApiResponse,
    dependencies=[Depends(require_feature("org_smtp_config"))],
)
async def test_smtp_config(
    org_id: str,
    body: SmtpTestRequest,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
):
    result = await db.execute(
        select(OrgSmtpConfig).where(
            OrgSmtpConfig.org_id == org_id,
            not_deleted(OrgSmtpConfig),
        )
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(404, detail={
            "error_code": 40450,
            "message_key": "errors.smtp.config_not_found",
            "message": "SMTP 配置不存在，请先保存配置",
        })

    from app.core.security import decrypt_sensitive
    from app.services.email.transport import SmtpConfig
    from app.services.email_service import send_test_email
    smtp = SmtpConfig(
        smtp_host=cfg.smtp_host,
        smtp_port=cfg.smtp_port,
        smtp_username=cfg.smtp_username,
        smtp_password=decrypt_sensitive(cfg.smtp_password_encrypted),
        from_email=cfg.from_email,
        from_name=cfg.from_name,
        use_tls=cfg.use_tls,
    )
    try:
        await send_test_email(body.recipient_email, smtp)
    except Exception as exc:
        logger.warning("SMTP test failed for org %s: %s", org_id, exc)
        raise HTTPException(400, detail={
            "error_code": 40051,
            "message_key": "errors.smtp.test_failed",
            "message": f"SMTP 测试失败: {exc}",
        })

    return ApiResponse(message="测试邮件已发送")
