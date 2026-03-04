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
from app.models.user import User
from app.schemas.admin import AdminCreateUserRequest, AdminUserResponse
from app.schemas.stocks import (
    AdminStockPageResponse,
    StockBasicSyncResponse,
    StockInstrumentResponse,
)
from app.services.auth_service import AuthError, register_user
from app.services.stock_sync_service import sync_stock_basic_full


router = APIRouter(prefix="/admin", tags=["admin"])
logger = get_logger("app.admin")
STOCK_BASIC_STATUSES = ("L", "D", "P", "G")


def _parse_stock_list_status_filter(value: str) -> list[str]:
    normalized_value = value.strip().upper()
    if not normalized_value or normalized_value == "ALL":
        return list(STOCK_BASIC_STATUSES)

    parsed: list[str] = []
    seen: set[str] = set()
    for raw_status in normalized_value.split(","):
        status_value = raw_status.strip()[:1]
        if status_value not in STOCK_BASIC_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid list_status, expected ALL or comma-separated values in L,D,P,G",
            )
        if status_value in seen:
            continue
        seen.add(status_value)
        parsed.append(status_value)

    return parsed or list(STOCK_BASIC_STATUSES)


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    _current_admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[AdminUserResponse]:
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
    list_statuses = _parse_stock_list_status_filter(list_status)
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


@router.get("/stocks", response_model=AdminStockPageResponse)
async def list_stocks(
    _current_admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    keyword: str | None = Query(default=None),
    list_status: str = Query(default="ALL"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> AdminStockPageResponse:
    list_statuses = _parse_stock_list_status_filter(list_status)
    statement = select(StockInstrument).where(
        StockInstrument.list_status.in_(list_statuses)
    )

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
