from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.analysis import StockAnalysisSummaryResponse
from app.services.analysis_service import get_stock_analysis_summary

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/stocks/{ts_code}/summary", response_model=StockAnalysisSummaryResponse)
async def get_stock_analysis_summary_route(
    ts_code: str,
    topic: str | None = Query(default=None),
    published_from: datetime | None = Query(default=None),
    published_to: datetime | None = Query(default=None),
    event_limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> StockAnalysisSummaryResponse:
    payload = await get_stock_analysis_summary(
        session,
        ts_code,
        topic=topic,
        published_from=published_from,
        published_to=published_to,
        event_limit=event_limit,
    )
    return StockAnalysisSummaryResponse.model_validate(payload)
