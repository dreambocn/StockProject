import sys
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin, analysis, auth, health, news, policy, stocks, watchlist
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
from app.db.session import dispose_engine
from app.db.init_db import ensure_database_schema


setup_logging()
logger = get_logger("app.request")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    is_pytest = "pytest" in sys.modules
    try:
        # 测试环境跳过 schema 检查，避免用例对真实基础设施产生副作用；
        # 其余环境统一走迁移模式判断，确保 API 与 Worker 对数据库状态的理解一致。
        if not is_pytest:
            await ensure_database_schema()

        yield
    finally:
        # 生命周期结束时主动释放连接池，避免开发环境关闭服务后数据库残留空闲连接。
        await dispose_engine()


app = FastAPI(title="Stock Project API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # 统一从配置读取 CORS 白名单，避免在代码里写死环境差异。
    allow_origins=settings.cors_allow_origins_list,
    allow_origin_regex=(settings.cors_allow_origin_regex or None),
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(stocks.router, prefix="/api", tags=["stocks"])
app.include_router(news.router, prefix="/api", tags=["news"])
app.include_router(policy.router, prefix="/api", tags=["policy"])
app.include_router(analysis.router, prefix="/api", tags=["analysis"])
app.include_router(watchlist.router, prefix="/api", tags=["watchlist"])
app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    # 为每个请求分配独立 request_id，并写入上下文用于全链路日志关联。
    request_id = uuid4().hex
    token = set_request_id(request_id)
    started = time.perf_counter()
    log_request_started(logger, request.method, request.url.path)

    try:
        response = await call_next(request)
    except Exception as exc:
        # 异常分支也记录耗时和 request_id，确保故障排查时链路完整。
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
        # 请求结束后必须重置上下文，避免 request_id 污染后续协程。
        reset_request_id(token)
