"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.annotations import router as annotations_router
from app.api.assets import router as assets_router
from app.api.auth import router as auth_router
from app.api.datasets import router as datasets_router
from app.api.project_classes import router as project_classes_router
from app.api.extract import router as extract_router
from app.api.folders import router as folders_router
from app.api.imports import router as imports_router
from app.api.jobs import router as jobs_router
from app.api.lineage import router as lineage_router
from app.api.projects import router as projects_router
from app.api.tags import router as tags_router
from app.api.versions import router as versions_router
# 注册 frame_extract / yolo_export / yolo_import 等 handlers
import app.jobs.handlers  # noqa: F401
from app.core.errors import AppError
from app.core.logging import get_logger, setup_logging
from app.core.middleware import RequestContextMiddleware
from app.core.config import get_settings
from app.jobs.service import reset_job_backend

logger = get_logger("labeltrace.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("api_starting job_backend=%s", settings.job_backend)
    # 触发 PgJobBackend 消费者启动
    from app.jobs.service import get_job_backend

    get_job_backend()
    yield
    logger.info("api_stopping")
    reset_job_backend()


app = FastAPI(
    title="LabelTrace API",
    version="0.1.0",
    description="视频优先的 YOLO 标注与数据集平台",
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5175",
        "http://localhost:38471",
        "http://127.0.0.1:38471",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(folders_router, prefix="/api/v1")
app.include_router(assets_router, prefix="/api/v1")
app.include_router(extract_router, prefix="/api/v1")
app.include_router(tags_router, prefix="/api/v1")
app.include_router(project_classes_router, prefix="/api/v1")
app.include_router(datasets_router, prefix="/api/v1")
app.include_router(imports_router, prefix="/api/v1")
app.include_router(annotations_router, prefix="/api/v1")
app.include_router(versions_router, prefix="/api/v1")
app.include_router(lineage_router, prefix="/api/v1")


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    logger.warning(
        "app_error code=%s status=%s msg=%s",
        exc.code,
        exc.status_code,
        exc.message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code, "details": exc.details},
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    if exc.status_code >= 500:
        logger.error("http_exception status=%s detail=%s", exc.status_code, exc.detail)
    else:
        logger.warning(
            "http_exception status=%s detail=%s", exc.status_code, exc.detail
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": "http_error"},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.warning("validation_error errors=%s", exc.errors())
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "code": "validation_error"},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    logger.exception("unhandled_exception type=%s", type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误", "code": "internal_error"},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "labeltrace-api"}
