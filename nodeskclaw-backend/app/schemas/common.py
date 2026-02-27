"""Common response schemas."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Unified API response wrapper."""

    code: int = 0
    error_code: int | None = None
    message_key: str | None = None
    message: str = "success"
    data: T | None = None


class Pagination(BaseModel):
    """Pagination metadata."""

    page: int = 1
    page_size: int = 20
    total: int = 0


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated API response."""

    code: int = 0
    error_code: int | None = None
    message_key: str | None = None
    message: str = "success"
    data: list[Any] = []
    pagination: Pagination = Pagination()
