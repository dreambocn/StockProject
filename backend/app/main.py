import sys
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, health, stocks
from app.core.logging import (
    get_logger,
    log_request_failed,
    log_request_finished,
    log_request_started,
    reset_request_id,
    set_request_id,
    setup_logging,
)
from app.core.settings import get_settings
from app.db.init_db import ensure_database_schema


setup_logging()
logger = get_logger("app.request")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    is_pytest = "pytest" in sys.modules
    if settings.db_auto_create_tables and not is_pytest:
        await ensure_database_schema()

    yield


app = FastAPI(title="Stock Project API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(stocks.router, prefix="/api", tags=["stocks"])
app.include_router(auth.router, prefix="/api")


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = uuid4().hex
    token = set_request_id(request_id)
    started = time.perf_counter()
    log_request_started(logger, request.method, request.url.path)

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = (time.perf_counter() - started) * 1000
        log_request_failed(logger, request.method, request.url.path, duration_ms, exc)
        raise
    else:
        duration_ms = (time.perf_counter() - started) * 1000
        log_request_finished(
            logger,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        reset_request_id(token)
