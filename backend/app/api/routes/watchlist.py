from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.watchlist import (
    WatchlistFeedResponse,
    WatchlistItemCreateRequest,
    WatchlistItemResponse,
    WatchlistItemUpdateRequest,
    WatchlistResponse,
)
from app.services.watchlist_service import (
    WatchlistConflictError,
    WatchlistNotFoundError,
    create_watchlist_item,
    delete_watchlist_item,
    get_watchlist_feed,
    list_watchlist,
    update_watchlist_item,
)


router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("", response_model=WatchlistResponse)
async def get_watchlist_route(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WatchlistResponse:
    # 鉴权边界：自选列表绑定当前用户，避免跨用户访问。
    payload = await list_watchlist(session, user_id=current_user.id)
    return WatchlistResponse.model_validate(payload)


@router.post(
    "/items",
    response_model=WatchlistItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_watchlist_item_route(
    request: WatchlistItemCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WatchlistItemResponse:
    try:
        payload = await create_watchlist_item(
            session,
            user_id=current_user.id,
            payload=request,
        )
    except WatchlistConflictError as exc:
        # 重复订阅属于冲突错误，返回 409 便于前端提示。
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WatchlistNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WatchlistItemResponse.model_validate(payload)


@router.patch("/items/{ts_code}", response_model=WatchlistItemResponse)
async def update_watchlist_item_route(
    ts_code: str,
    request: WatchlistItemUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WatchlistItemResponse:
    try:
        payload = await update_watchlist_item(
            session,
            user_id=current_user.id,
            ts_code=ts_code,
            payload=request,
        )
    except WatchlistNotFoundError as exc:
        # 用户未订阅该标的时返回 404，避免误导为成功更新。
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WatchlistItemResponse.model_validate(payload)


@router.delete("/items/{ts_code}", response_model=MessageResponse)
async def delete_watchlist_item_route(
    ts_code: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    try:
        await delete_watchlist_item(
            session,
            user_id=current_user.id,
            ts_code=ts_code,
        )
    except WatchlistNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # 删除成功返回统一 message，前端无需关心实现细节。
    return MessageResponse(message="watchlist item deleted")


@router.get("/feed", response_model=WatchlistFeedResponse)
async def get_watchlist_feed_route(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WatchlistFeedResponse:
    payload = await get_watchlist_feed(session, user_id=current_user.id)
    return WatchlistFeedResponse.model_validate(payload)
