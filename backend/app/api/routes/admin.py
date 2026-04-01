from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_admin
from app.core.logging import get_logger
from app.core.settings import get_settings
from app.db.session import get_db_session
from app.integrations.tushare_gateway import TushareGateway
from app.models.stock_instrument import StockInstrument
from app.models.system_job_run import SystemJobRun
from app.models.user import User
from app.schemas.admin import AdminCreateUserRequest, AdminUserResponse
from app.schemas.admin_jobs import (
    AdminJobDetailResponse,
    AdminJobFailureSummaryResponse,
    AdminJobLinkedEntityResponse,
    AdminJobListItemResponse,
    AdminJobPageResponse,
    AdminJobSummaryResponse,
)
from app.schemas.policy import AdminPolicySyncResponse, PolicySyncRequest
from app.schemas.stocks import (
    AdminStockPageResponse,
    StockBasicSyncResponse,
    StockInstrumentResponse,
)
from app.services.auth_service import AuthError, register_user
from app.services.stock_list_status import (
    STOCK_BASIC_STATUSES,
    parse_stock_list_status_filter,
)
from app.services.stock_sync_service import sync_stock_basic_full
from app.services.policy_sync_service import sync_policy_documents
from app.services.job_query_service import (
    get_job_status_counts,
    get_job_type_counts,
    list_job_runs,
    list_recent_failed_jobs,
)


router = APIRouter(prefix="/admin", tags=["admin"])
logger = get_logger("app.admin")


def _serialize_admin_job_item(job: SystemJobRun) -> AdminJobListItemResponse:
    return AdminJobListItemResponse(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        trigger_source=job.trigger_source,
        resource_type=job.resource_type,
        resource_key=job.resource_key,
        summary=job.summary,
        linked_entity=AdminJobLinkedEntityResponse(
            entity_type=job.linked_entity_type,
            entity_id=job.linked_entity_id,
        ),
        started_at=job.started_at,
        heartbeat_at=job.heartbeat_at,
        finished_at=job.finished_at,
        duration_ms=job.duration_ms,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    _current_admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[AdminUserResponse]:
    # 管理台仅列出最近创建的用户，便于审计与人工排查。
    statement = select(User).order_by(User.created_at.desc())
    result = await session.execute(statement)
    users = result.scalars().all()
    return [AdminUserResponse.model_validate(user) for user in users]


@router.post(
    "/users", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED
)
async def create_user(
    payload: AdminCreateUserRequest,
    current_admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminUserResponse:
    try:
        # 关键业务分支：账号创建统一复用 auth service，保证唯一性校验与密码哈希策略一致。
        user = await register_user(
            session,
            username=payload.username,
            email=payload.email,
            password=payload.password,
            user_level=payload.user_level,
        )
    except AuthError as exc:
        logger.warning(
            "event=admin.user.create.failed admin_id=%s username=%s reason=%s",
            current_admin.id,
            payload.username,
            exc.detail,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    logger.info(
        "event=admin.user.create.success admin_id=%s created_user_id=%s user_level=%s",
        current_admin.id,
        user.id,
        user.user_level,
    )
    return AdminUserResponse.model_validate(user)


@router.post("/stocks/full", response_model=StockBasicSyncResponse)
async def sync_stocks_full(
    _current_admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    list_status: str = Query(default="ALL"),
) -> StockBasicSyncResponse:
    settings = get_settings()
    try:
        # 安全边界：Tushare token 仅从服务端配置读取，禁止在路由或前端写死凭据。
        gateway = TushareGateway(settings.tushare_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tushare token not configured",
        ) from exc

    # 关键副作用：该接口会触发全量入库同步，返回结果用于确认本次写库规模与状态范围。
    try:
        list_statuses = parse_stock_list_status_filter(
            list_status,
            all_statuses=STOCK_BASIC_STATUSES,
            default_statuses=STOCK_BASIC_STATUSES,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    sync_result = await sync_stock_basic_full(
        session,
        gateway,
        list_statuses=list_statuses,
    )
    return StockBasicSyncResponse(
        message="stock basic sync completed",
        total=int(sync_result["total"]),
        created=int(sync_result["created"]),
        updated=int(sync_result["updated"]),
        list_statuses=list(sync_result["list_statuses"]),
    )


@router.post("/policy/sync", response_model=AdminPolicySyncResponse)
async def sync_policy_documents_route(
    payload: PolicySyncRequest,
    _current_admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminPolicySyncResponse:
    # 关键流程：后台手动同步统一复用政策同步服务，避免脚本入口和 API 入口产生两套口径。
    result = await sync_policy_documents(
        session,
        trigger_source="admin.policy.sync",
        force_refresh=payload.force_refresh,
    )
    return AdminPolicySyncResponse(
        job_id=str(result.get("job_id") or ""),
        job_type="policy_sync",
        status=str(result["status"]),
        provider_count=int(result["provider_count"]),
        raw_count=int(result["raw_count"]),
        normalized_count=int(result["normalized_count"]),
        inserted_count=int(result["inserted_count"]),
        updated_count=int(result["updated_count"]),
        deduped_count=int(result["deduped_count"]),
        failed_provider_count=int(result["failed_provider_count"]),
    )


@router.get("/stocks", response_model=AdminStockPageResponse)
async def list_stocks(
    _current_admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    keyword: str | None = Query(default=None),
    list_status: str = Query(default="ALL"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> AdminStockPageResponse:
    try:
        list_statuses = parse_stock_list_status_filter(
            list_status,
            all_statuses=STOCK_BASIC_STATUSES,
            default_statuses=STOCK_BASIC_STATUSES,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    statement = select(StockInstrument).where(
        StockInstrument.list_status.in_(list_statuses)
    )

    # 关键过滤：关键词允许 ts_code/symbol/name 联合检索，方便后台定位异常标的。
    normalized_keyword = keyword.strip() if keyword else ""
    if normalized_keyword:
        wildcard = f"%{normalized_keyword}%"
        statement = statement.where(
            or_(
                StockInstrument.ts_code.ilike(wildcard),
                StockInstrument.symbol.ilike(wildcard),
                StockInstrument.name.ilike(wildcard),
            )
        )

    total_statement = select(func.count()).select_from(statement.subquery())
    total = int((await session.execute(total_statement)).scalar_one())

    # 关键流程：默认查询只走数据库分页，避免每次列表刷新都触发外部数据源请求。
    paged_statement = (
        statement.order_by(StockInstrument.ts_code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    instruments = (await session.execute(paged_statement)).scalars().all()
    return AdminStockPageResponse(
        items=[StockInstrumentResponse.model_validate(item) for item in instruments],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/jobs", response_model=AdminJobPageResponse)
async def list_jobs(
    _current_admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    job_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    trigger_source: str | None = Query(default=None),
    resource_key: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    started_from: datetime | None = Query(default=None),
    started_to: datetime | None = Query(default=None),
) -> AdminJobPageResponse:
    items, total = await list_job_runs(
        session,
        job_type=job_type,
        status=status,
        trigger_source=trigger_source,
        resource_key=resource_key,
        page=page,
        page_size=page_size,
        started_from=started_from,
        started_to=started_to,
    )
    return AdminJobPageResponse(
        items=[_serialize_admin_job_item(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/jobs/summary", response_model=AdminJobSummaryResponse)
async def get_jobs_summary(
    _current_admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminJobSummaryResponse:
    status_counts = await get_job_status_counts(session)
    type_counts = await get_job_type_counts(session)
    recent_failures = await list_recent_failed_jobs(session)
    total = sum(status_counts.values())
    return AdminJobSummaryResponse(
        total=total,
        status_counts=status_counts,
        type_counts=type_counts,
        recent_failures=[
            AdminJobFailureSummaryResponse(
                id=item.id,
                job_type=item.job_type,
                trigger_source=item.trigger_source,
                resource_key=item.resource_key,
                error_type=item.error_type,
                error_message=item.error_message,
                finished_at=item.finished_at,
            )
            for item in recent_failures
        ],
    )


@router.get("/jobs/{job_id}", response_model=AdminJobDetailResponse)
async def get_job_detail(
    job_id: str,
    _current_admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminJobDetailResponse:
    job = await session.get(SystemJobRun, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")

    base_item = _serialize_admin_job_item(job)
    return AdminJobDetailResponse(
        **base_item.model_dump(),
        idempotency_key=job.idempotency_key,
        payload_json=job.payload_json,
        metrics_json=job.metrics_json,
        error_type=job.error_type,
        error_message=job.error_message,
    )
