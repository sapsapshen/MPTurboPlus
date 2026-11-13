"""Application implementation - ASGI."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.config import config
from app.models.exception import HttpException
from app.router import root_api_router
from app.utils import utils


def exception_handler(request: Request, e: HttpException):
    return JSONResponse(
        status_code=e.status_code,
        content=utils.get_response(e.status_code, e.data, e.message),
    )


def _validation_error_message(errors: list) -> str:
    if not errors:
        return "request validation failed"

    first = errors[0]
    detail = str(first.get("msg") or "request validation failed")
    location = ".".join(
        str(part)
        for part in first.get("loc", [])
        if part not in {"body", "query", "path"}
    )
    if location:
        return f"{location}: {detail}"
    return detail


def validation_exception_handler(request: Request, e: RequestValidationError):
    errors = e.errors()
    return JSONResponse(
        status_code=400,
        content=utils.get_response(
            status=400,
            data=errors,
            message=_validation_error_message(errors),
        ),
    )


def resolve_cors_settings(allowed_origins: str | None) -> tuple[list[str], bool]:
    """Return allowed origins and whether credentialed browser requests are enabled.

    Browsers reject `Access-Control-Allow-Origin: *` together with
    `Access-Control-Allow-Credentials: true`. An empty setting keeps the API
    callable from any origin. Credentials are enabled only when the operator
    lists explicit origins.
    """
    raw_origins = (allowed_origins or "").strip()
    if not raw_origins:
        origins = ["*"]
    else:
        origins = [item.strip() for item in raw_origins.split(",") if item.strip()]
    # 只要列表里出现 *，浏览器就不允许同时开启 credentials。
    if not origins or "*" in origins:
        return ["*"], False
    return origins, True


@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    logger.info("startup event")
    yield
    logger.info("shutdown event")


def get_application() -> FastAPI:
    """Initialize FastAPI application.

    Returns:
       FastAPI: Application object instance.

    """
    instance = FastAPI(
        title=config.project_name,
        description=config.project_description,
        version=config.project_version,
        debug=False,
        lifespan=app_lifespan,
    )
    instance.include_router(root_api_router)
    instance.add_exception_handler(HttpException, exception_handler)
    instance.add_exception_handler(RequestValidationError, validation_exception_handler)
    return instance


app = get_application()

# Configures the CORS middleware for the FastAPI app
origins, allow_credentials = resolve_cors_settings(os.getenv("CORS_ALLOWED_ORIGINS", ""))
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

task_dir = utils.task_dir()
app.mount(
    "/tasks", StaticFiles(directory=task_dir, html=True, follow_symlink=True), name=""
)

public_dir = utils.public_dir()
app.mount("/", StaticFiles(directory=public_dir, html=True), name="")
