"""Organization-scoped runtime image build endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import hooks
from app.core.deps import get_current_org, get_db
from app.schemas.cluster import ClusterInfo
from app.schemas.common import ApiResponse
from app.schemas.image_build import ImageBuildCreate, ImageBuildInfo, ImageBuildSummary
from app.services import image_build_service

image_build_read_router = APIRouter()
image_build_write_router = APIRouter()


@image_build_read_router.get("", response_model=ApiResponse[list[ImageBuildSummary]])
async def list_image_builds(
    runtime: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    _user, org = org_ctx
    builds = await image_build_service.list_builds(
        org_id=org.id,
        runtime=runtime,
        db=db,
    )
    return ApiResponse(data=[ImageBuildSummary.model_validate(build) for build in builds])


@image_build_read_router.get(
    "/eligible-clusters",
    response_model=ApiResponse[list[ClusterInfo]],
)
async def list_image_build_clusters(
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    from app.services import cluster_service

    _user, org = org_ctx
    clusters = await cluster_service.list_clusters(db, org.id)
    return ApiResponse(data=clusters)


@image_build_read_router.get("/{build_id}", response_model=ApiResponse[ImageBuildInfo])
async def get_image_build(
    build_id: str,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    _user, org = org_ctx
    build = await image_build_service.get_build(build_id, org_id=org.id, db=db)
    build = await image_build_service.refresh_build(build, db)
    await db.commit()
    return ApiResponse(data=ImageBuildInfo.model_validate(build))


@image_build_read_router.get("/{build_id}/logs", response_model=ApiResponse[ImageBuildInfo])
async def get_image_build_logs(
    build_id: str,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    _user, org = org_ctx
    build = await image_build_service.get_build(build_id, org_id=org.id, db=db)
    build = await image_build_service.refresh_build_logs(build, db)
    await db.commit()
    return ApiResponse(data=ImageBuildInfo.model_validate(build))


@image_build_write_router.post("", response_model=ApiResponse[ImageBuildInfo])
async def create_image_build(
    body: ImageBuildCreate,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    user, org = org_ctx
    build = await image_build_service.start_build(
        runtime=body.runtime,
        version=body.version,
        cluster_id=body.cluster_id,
        source_ref=body.source_ref,
        release_notes=body.release_notes,
        user_id=user.id,
        org_id=org.id,
        db=db,
    )
    await db.commit()
    await hooks.emit(
        "operation_audit",
        action="image_build.created",
        target_type="image_build",
        target_id=build.id,
        actor_id=user.id,
        org_id=org.id,
        details={
            "runtime": build.runtime,
            "version": build.version,
            "cluster_id": build.cluster_id,
        },
    )
    return ApiResponse(data=ImageBuildInfo.model_validate(build))
