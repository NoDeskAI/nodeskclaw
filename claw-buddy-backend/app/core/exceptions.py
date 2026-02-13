"""Unified exception handling."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    """Base application exception."""

    def __init__(self, code: int, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code


class NotFoundError(AppException):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(code=40400, message=message, status_code=404)


class ForbiddenError(AppException):
    def __init__(self, message: str = "无权限"):
        super().__init__(code=40300, message=message, status_code=403)


class BadRequestError(AppException):
    def __init__(self, message: str = "请求参数错误"):
        super().__init__(code=40000, message=message, status_code=400)


class ConflictError(AppException):
    def __init__(self, message: str = "资源冲突"):
        super().__init__(code=40900, message=message, status_code=409)


class K8sError(AppException):
    def __init__(self, message: str = "K8s 操作失败"):
        super().__init__(code=50010, message=message, status_code=502)


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(AppException)
    async def app_exception_handler(_request: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "data": None},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"code": 50000, "message": f"服务器内部错误: {exc}", "data": None},
        )
