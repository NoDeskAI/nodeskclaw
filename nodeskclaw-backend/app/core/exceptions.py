"""Unified exception handling."""

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        code: int,
        message: str,
        status_code: int = 400,
        message_key: str | None = None,
        error_code: int | None = None,
        message_params: dict[str, str] | None = None,
    ):
        self.code = code
        self.error_code = error_code if error_code is not None else code
        self.message = message
        self.message_key = message_key
        self.message_params = message_params
        self.status_code = status_code


class NotFoundError(AppException):
    def __init__(self, message: str = "资源不存在", message_key: str = "errors.common.not_found"):
        super().__init__(code=40400, message=message, status_code=404, message_key=message_key)


class ForbiddenError(AppException):
    def __init__(self, message: str = "无权限", message_key: str = "errors.common.forbidden"):
        super().__init__(code=40300, message=message, status_code=403, message_key=message_key)


class BadRequestError(AppException):
    def __init__(
        self,
        message: str = "请求参数错误",
        message_key: str = "errors.common.bad_request",
        message_params: dict[str, str] | None = None,
    ):
        super().__init__(
            code=40000, message=message, status_code=400,
            message_key=message_key, message_params=message_params,
        )


class ConflictError(AppException):
    def __init__(
        self,
        message: str = "资源冲突",
        message_key: str = "errors.common.conflict",
        message_params: dict[str, str] | None = None,
    ):
        super().__init__(
            code=40900, message=message, status_code=409,
            message_key=message_key, message_params=message_params,
        )


class K8sError(AppException):
    def __init__(self, message: str = "K8s 操作失败", message_key: str = "errors.k8s.operation_failed"):
        super().__init__(code=50010, message=message, status_code=502, message_key=message_key)


HTTP_STATUS_DEFAULT_CODES: dict[int, int] = {
    400: 40000,
    401: 40100,
    403: 40300,
    404: 40400,
    409: 40900,
    422: 42200,
    500: 50000,
    502: 50200,
    503: 50300,
}


def _default_code_by_status(status_code: int) -> int:
    return HTTP_STATUS_DEFAULT_CODES.get(status_code, status_code * 100)


def _normalize_http_detail(detail: Any, status_code: int) -> tuple[int, str, str]:
    default_code = _default_code_by_status(status_code)
    default_key = f"errors.http.status_{status_code}"
    default_message = "请求失败"
    if detail is None:
        return default_code, default_key, default_message

    if isinstance(detail, dict):
        error_code = detail.get("error_code") or detail.get("code") or default_code
        message_key = detail.get("message_key") or default_key
        message = detail.get("message") or detail.get("detail") or default_message
        return int(error_code), str(message_key), str(message)

    if isinstance(detail, str):
        return default_code, default_key, detail

    return default_code, default_key, default_message


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(AppException)
    async def app_exception_handler(_request: Request, exc: AppException) -> JSONResponse:
        body: dict[str, Any] = {
            "code": exc.code,
            "error_code": exc.error_code,
            "message_key": exc.message_key,
            "message": exc.message,
            "data": None,
        }
        if exc.message_params:
            body["message_params"] = exc.message_params
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        error_code, message_key, message = _normalize_http_detail(exc.detail, exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": error_code,
                "error_code": error_code,
                "message_key": message_key,
                "message": message,
                "data": None,
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=500,
            content={
                "code": 50000,
                "error_code": 50000,
                "message_key": "errors.system.internal_error",
                "message": "服务器内部错误",
                "data": None,
            },
        )
