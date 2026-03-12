"""Portal-accessible engine listing endpoint."""

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.runtime.registries.runtime_registry import RUNTIME_REGISTRY

router = APIRouter()


@router.get("", response_model=ApiResponse[list])
async def list_engines(_user: User = Depends(get_current_user)):
    engines = []
    for spec in RUNTIME_REGISTRY.all_runtimes():
        engines.append({
            "runtime_id": spec.runtime_id,
            "display_name": spec.display_name,
            "display_description": spec.display_description,
            "display_tags": list(spec.display_tags),
            "display_powered_by": spec.display_powered_by,
            "order": spec.order,
        })
    engines.sort(key=lambda r: r["order"])
    return ApiResponse(data=engines)
