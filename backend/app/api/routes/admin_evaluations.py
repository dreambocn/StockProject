from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_admin
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.admin_evaluations import (
    EvaluationCatalogResponse,
    EvaluationCaseDetailResponse,
    EvaluationOverviewResponse,
)
from app.services.analysis_evaluation_repository import (
    build_evaluation_case_detail,
    build_evaluation_catalog,
    build_evaluation_overview,
)


router = APIRouter(prefix='/admin/evaluations', tags=['admin-evaluations'])


@router.get('/catalog', response_model=EvaluationCatalogResponse)
async def get_evaluation_catalog_route(
    _current_admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EvaluationCatalogResponse:
    payload = await build_evaluation_catalog(session)
    return EvaluationCatalogResponse.model_validate(payload)


@router.get('/overview', response_model=EvaluationOverviewResponse)
async def get_evaluation_overview_route(
    _current_admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    dataset_key: str = Query(...),
    experiment_group_key: str = Query(...),
    baseline_run_id: str | None = Query(default=None),
    candidate_run_id: str | None = Query(default=None),
) -> EvaluationOverviewResponse:
    try:
        payload = await build_evaluation_overview(
            session,
            dataset_key=dataset_key,
            experiment_group_key=experiment_group_key,
            baseline_run_id=baseline_run_id,
            candidate_run_id=candidate_run_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return EvaluationOverviewResponse.model_validate(payload)


@router.get('/cases/{case_key}', response_model=EvaluationCaseDetailResponse)
async def get_evaluation_case_detail_route(
    case_key: str,
    _current_admin: Annotated[User, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    baseline_run_id: str = Query(...),
    candidate_run_id: str = Query(...),
) -> EvaluationCaseDetailResponse:
    try:
        payload = await build_evaluation_case_detail(
            session,
            case_key=case_key,
            baseline_run_id=baseline_run_id,
            candidate_run_id=candidate_run_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if '样本不存在' in detail else 422
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return EvaluationCaseDetailResponse.model_validate(payload)
