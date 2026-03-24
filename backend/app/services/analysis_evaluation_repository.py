from collections.abc import Iterable
from datetime import date, datetime
import re

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_evaluation_case import AnalysisEvaluationCase
from app.models.analysis_evaluation_case_result import AnalysisEvaluationCaseResult
from app.models.analysis_evaluation_dataset import AnalysisEvaluationDataset
from app.models.analysis_evaluation_run import AnalysisEvaluationRun


METRIC_CARD_META = {
    'event_top1_hit_rate': {'label': '事件关联命中率', 'unit': 'rate'},
    'factor_top1_accuracy': {'label': 'Top1 因子命中率', 'unit': 'rate'},
    'citation_metadata_completeness_rate': {
        'label': '引用元数据完整率',
        'unit': 'rate',
    },
    'avg_latency_ms': {'label': '平均分析耗时', 'unit': 'ms'},
}


def normalize_evaluation_title(title: str | None) -> str:
    normalized = (title or '').strip().lower()
    normalized = re.sub(r'[\s\W_]+', '', normalized, flags=re.UNICODE)
    return normalized


def calculate_case_score(
    *,
    event_top1_hit: bool,
    factor_top1_hit: bool,
    citation_metadata_completeness_rate: float,
) -> float:
    return round(
        0.45 * float(bool(event_top1_hit))
        + 0.35 * float(bool(factor_top1_hit))
        + 0.20 * max(0.0, min(float(citation_metadata_completeness_rate), 1.0)),
        4,
    )


def classify_case_result(*, baseline_score: float, candidate_score: float) -> str:
    if candidate_score > baseline_score:
        return 'improved'
    if candidate_score < baseline_score:
        return 'regressed'
    return 'unchanged'


def _serialize_dataset(dataset: AnalysisEvaluationDataset) -> dict[str, object]:
    return {
        'id': dataset.id,
        'dataset_key': dataset.dataset_key,
        'label': dataset.label,
        'description': dataset.description,
        'sample_count': dataset.sample_count,
        'date_from': dataset.date_from,
        'date_to': dataset.date_to,
    }


def _serialize_run_summary(run: AnalysisEvaluationRun | None) -> dict[str, object] | None:
    if run is None:
        return None
    return {
        'id': run.id,
        'run_key': run.run_key,
        'experiment_group_key': run.experiment_group_key,
        'variant_key': run.variant_key,
        'variant_label': run.variant_label,
        'prompt_profile_key': run.prompt_profile_key,
        'model_name': run.model_name,
        'sample_count': run.sample_count,
        'event_top1_hit_rate': run.event_top1_hit_rate,
        'factor_top1_accuracy': run.factor_top1_accuracy,
        'citation_metadata_completeness_rate': run.citation_metadata_completeness_rate,
        'avg_latency_ms': run.avg_latency_ms,
        'created_at': run.created_at,
    }


def _build_metric_cards(
    baseline_run: AnalysisEvaluationRun,
    candidate_run: AnalysisEvaluationRun,
) -> dict[str, dict[str, object]]:
    metric_cards: dict[str, dict[str, object]] = {}
    for metric_key, meta in METRIC_CARD_META.items():
        metric_cards[metric_key] = {
            'metric_key': metric_key,
            'label': meta['label'],
            'unit': meta['unit'],
            'baseline_value': getattr(baseline_run, metric_key),
            'candidate_value': getattr(candidate_run, metric_key),
        }
    return metric_cards


def _build_bar_chart_payload(
    baseline_run: AnalysisEvaluationRun,
    candidate_run: AnalysisEvaluationRun,
) -> dict[str, object]:
    categories: list[str] = []
    baseline_values: list[float] = []
    candidate_values: list[float] = []
    for metric_key, meta in METRIC_CARD_META.items():
        categories.append(str(meta['label']))
        baseline_values.append(float(getattr(baseline_run, metric_key)))
        candidate_values.append(float(getattr(candidate_run, metric_key)))
    return {
        'categories': categories,
        'baseline_series': baseline_values,
        'candidate_series': candidate_values,
    }


async def upsert_evaluation_dataset(
    session: AsyncSession,
    *,
    dataset_key: str,
    label: str,
    description: str | None,
    sample_count: int,
    date_from: date | None,
    date_to: date | None,
) -> AnalysisEvaluationDataset:
    statement = select(AnalysisEvaluationDataset).where(
        AnalysisEvaluationDataset.dataset_key == dataset_key
    )
    row = (await session.execute(statement)).scalar_one_or_none()
    if row is None:
        row = AnalysisEvaluationDataset(dataset_key=dataset_key)
        session.add(row)
    row.label = label
    row.description = description
    row.sample_count = sample_count
    row.date_from = date_from
    row.date_to = date_to
    await session.flush()
    return row


async def upsert_evaluation_case(
    session: AsyncSession,
    *,
    dataset_id: str,
    case_key: str,
    ts_code: str,
    topic: str | None,
    anchor_event_title: str,
    expected_top_factor_key: str,
    notes: str | None,
) -> AnalysisEvaluationCase:
    statement = select(AnalysisEvaluationCase).where(
        AnalysisEvaluationCase.case_key == case_key
    )
    row = (await session.execute(statement)).scalar_one_or_none()
    if row is None:
        row = AnalysisEvaluationCase(case_key=case_key)
        session.add(row)
    row.dataset_id = dataset_id
    row.ts_code = ts_code
    row.topic = topic
    row.anchor_event_title = anchor_event_title
    row.expected_top_factor_key = expected_top_factor_key
    row.notes = notes
    await session.flush()
    return row


async def create_evaluation_run(
    session: AsyncSession,
    *,
    run_key: str,
    dataset_id: str,
    experiment_group_key: str,
    variant_key: str,
    variant_label: str,
    prompt_profile_key: str,
    model_name: str,
    sample_count: int,
    event_top1_hit_rate: float,
    factor_top1_accuracy: float,
    citation_metadata_completeness_rate: float,
    avg_latency_ms: float,
    created_at: datetime | None = None,
) -> AnalysisEvaluationRun:
    row = AnalysisEvaluationRun(
        run_key=run_key,
        dataset_id=dataset_id,
        experiment_group_key=experiment_group_key,
        variant_key=variant_key,
        variant_label=variant_label,
        prompt_profile_key=prompt_profile_key,
        model_name=model_name,
        sample_count=sample_count,
        event_top1_hit_rate=event_top1_hit_rate,
        factor_top1_accuracy=factor_top1_accuracy,
        citation_metadata_completeness_rate=citation_metadata_completeness_rate,
        avg_latency_ms=avg_latency_ms,
        created_at=created_at or datetime.utcnow(),
    )
    session.add(row)
    await session.flush()
    return row


async def upsert_evaluation_case_result(
    session: AsyncSession,
    *,
    run_id: str,
    case_id: str,
    event_top1_hit: bool,
    factor_top1_hit: bool,
    citation_metadata_completeness_rate: float,
    latency_ms: float,
    top_event_title: str | None,
    top_factor_key: str | None,
    web_source_count: int,
    result_snapshot: dict[str, object] | None,
) -> AnalysisEvaluationCaseResult:
    statement = (
        select(AnalysisEvaluationCaseResult)
        .where(AnalysisEvaluationCaseResult.run_id == run_id)
        .where(AnalysisEvaluationCaseResult.case_id == case_id)
    )
    row = (await session.execute(statement)).scalar_one_or_none()
    if row is None:
        row = AnalysisEvaluationCaseResult(run_id=run_id, case_id=case_id)
        session.add(row)
    row.event_top1_hit = event_top1_hit
    row.factor_top1_hit = factor_top1_hit
    row.citation_metadata_completeness_rate = citation_metadata_completeness_rate
    row.latency_ms = latency_ms
    row.top_event_title = top_event_title
    row.top_factor_key = top_factor_key
    row.web_source_count = web_source_count
    row.result_snapshot = result_snapshot
    await session.flush()
    return row


async def load_evaluation_dataset_by_key(
    session: AsyncSession,
    dataset_key: str,
) -> AnalysisEvaluationDataset | None:
    statement = select(AnalysisEvaluationDataset).where(
        AnalysisEvaluationDataset.dataset_key == dataset_key
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def list_evaluation_cases_by_dataset(
    session: AsyncSession,
    dataset_id: str,
) -> list[AnalysisEvaluationCase]:
    statement = (
        select(AnalysisEvaluationCase)
        .where(AnalysisEvaluationCase.dataset_id == dataset_id)
        .order_by(AnalysisEvaluationCase.case_key.asc())
    )
    return (await session.execute(statement)).scalars().all()


async def load_evaluation_case_by_key(
    session: AsyncSession,
    case_key: str,
) -> AnalysisEvaluationCase | None:
    statement = select(AnalysisEvaluationCase).where(
        AnalysisEvaluationCase.case_key == case_key
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def load_latest_evaluation_run(
    session: AsyncSession,
    *,
    dataset_id: str,
    experiment_group_key: str,
    variant_key: str,
) -> AnalysisEvaluationRun | None:
    statement = (
        select(AnalysisEvaluationRun)
        .where(AnalysisEvaluationRun.dataset_id == dataset_id)
        .where(AnalysisEvaluationRun.experiment_group_key == experiment_group_key)
        .where(AnalysisEvaluationRun.variant_key == variant_key)
        .order_by(AnalysisEvaluationRun.created_at.desc(), AnalysisEvaluationRun.id.desc())
        .limit(1)
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def load_evaluation_run_by_id(
    session: AsyncSession,
    run_id: str,
) -> AnalysisEvaluationRun | None:
    return await session.get(AnalysisEvaluationRun, run_id)


async def list_evaluation_case_results_by_run(
    session: AsyncSession,
    run_id: str,
) -> list[AnalysisEvaluationCaseResult]:
    statement = (
        select(AnalysisEvaluationCaseResult)
        .where(AnalysisEvaluationCaseResult.run_id == run_id)
        .order_by(AnalysisEvaluationCaseResult.case_id.asc())
    )
    return (await session.execute(statement)).scalars().all()


async def build_evaluation_catalog(session: AsyncSession) -> dict[str, object]:
    dataset_rows = (
        await session.execute(
            select(AnalysisEvaluationDataset).order_by(
                AnalysisEvaluationDataset.created_at.desc(),
                AnalysisEvaluationDataset.dataset_key.asc(),
            )
        )
    ).scalars().all()
    run_rows = (
        await session.execute(
            select(AnalysisEvaluationRun).order_by(
                AnalysisEvaluationRun.created_at.desc(),
                AnalysisEvaluationRun.id.desc(),
            )
        )
    ).scalars().all()

    dataset_id_to_key = {row.id: row.dataset_key for row in dataset_rows}
    group_map: dict[tuple[str, str], dict[str, object]] = {}
    for run in run_rows:
        dataset_key = dataset_id_to_key.get(run.dataset_id)
        if not dataset_key:
            continue
        map_key = (dataset_key, run.experiment_group_key)
        group_entry = group_map.setdefault(
            map_key,
            {
                'dataset_key': dataset_key,
                'experiment_group_key': run.experiment_group_key,
                'latest_baseline_run': None,
                'latest_candidate_run': None,
                'baseline_runs': [],
                'candidate_runs': [],
            },
        )
        if run.variant_key == 'baseline' and group_entry['latest_baseline_run'] is None:
            group_entry['latest_baseline_run'] = _serialize_run_summary(run)
        if run.variant_key == 'optimized' and group_entry['latest_candidate_run'] is None:
            group_entry['latest_candidate_run'] = _serialize_run_summary(run)
        if run.variant_key == 'baseline':
            group_entry['baseline_runs'].append(_serialize_run_summary(run))
        if run.variant_key == 'optimized':
            group_entry['candidate_runs'].append(_serialize_run_summary(run))

    return {
        'datasets': [_serialize_dataset(row) for row in dataset_rows],
        'experiment_groups': list(group_map.values()),
    }


async def _resolve_run_pair(
    session: AsyncSession,
    *,
    dataset: AnalysisEvaluationDataset | None,
    experiment_group_key: str | None,
    baseline_run_id: str | None,
    candidate_run_id: str | None,
) -> tuple[AnalysisEvaluationRun | None, AnalysisEvaluationRun | None]:
    if baseline_run_id or candidate_run_id:
        if not baseline_run_id or not candidate_run_id:
            raise ValueError('baseline_run_id 和 candidate_run_id 必须同时提供')
        baseline_run = await load_evaluation_run_by_id(session, baseline_run_id)
        candidate_run = await load_evaluation_run_by_id(session, candidate_run_id)
        if baseline_run is None or candidate_run is None:
            raise ValueError('指定的实验运行不存在')
        return baseline_run, candidate_run

    if dataset is None or not experiment_group_key:
        return None, None

    baseline_run = await load_latest_evaluation_run(
        session,
        dataset_id=dataset.id,
        experiment_group_key=experiment_group_key,
        variant_key='baseline',
    )
    candidate_run = await load_latest_evaluation_run(
        session,
        dataset_id=dataset.id,
        experiment_group_key=experiment_group_key,
        variant_key='optimized',
    )
    if baseline_run is None and candidate_run is None:
        return None, None
    if baseline_run is None or candidate_run is None:
        raise ValueError('当前实验组缺少完整的 baseline/optimized 结果对')
    return baseline_run, candidate_run


def _index_case_results(
    rows: Iterable[AnalysisEvaluationCaseResult],
) -> dict[str, AnalysisEvaluationCaseResult]:
    return {row.case_id: row for row in rows}


def _serialize_case_comparison(
    evaluation_case: AnalysisEvaluationCase,
    baseline_result: AnalysisEvaluationCaseResult | None,
    candidate_result: AnalysisEvaluationCaseResult | None,
) -> dict[str, object]:
    baseline_score = calculate_case_score(
        event_top1_hit=bool(getattr(baseline_result, 'event_top1_hit', False)),
        factor_top1_hit=bool(getattr(baseline_result, 'factor_top1_hit', False)),
        citation_metadata_completeness_rate=float(
            getattr(baseline_result, 'citation_metadata_completeness_rate', 0.0) or 0.0
        ),
    )
    candidate_score = calculate_case_score(
        event_top1_hit=bool(getattr(candidate_result, 'event_top1_hit', False)),
        factor_top1_hit=bool(getattr(candidate_result, 'factor_top1_hit', False)),
        citation_metadata_completeness_rate=float(
            getattr(candidate_result, 'citation_metadata_completeness_rate', 0.0) or 0.0
        ),
    )
    classification = classify_case_result(
        baseline_score=baseline_score,
        candidate_score=candidate_score,
    )
    return {
        'case_key': evaluation_case.case_key,
        'ts_code': evaluation_case.ts_code,
        'topic': evaluation_case.topic,
        'anchor_event_title': evaluation_case.anchor_event_title,
        'expected_top_factor_key': evaluation_case.expected_top_factor_key,
        'notes': evaluation_case.notes,
        'baseline_score': baseline_score,
        'candidate_score': candidate_score,
        'score_delta': round(candidate_score - baseline_score, 4),
        'classification': classification,
        'baseline_top_event_title': getattr(baseline_result, 'top_event_title', None),
        'candidate_top_event_title': getattr(candidate_result, 'top_event_title', None),
        'baseline_top_factor_key': getattr(baseline_result, 'top_factor_key', None),
        'candidate_top_factor_key': getattr(candidate_result, 'top_factor_key', None),
        'baseline_citation_metadata_completeness_rate': float(
            getattr(baseline_result, 'citation_metadata_completeness_rate', 0.0) or 0.0
        ),
        'candidate_citation_metadata_completeness_rate': float(
            getattr(candidate_result, 'citation_metadata_completeness_rate', 0.0) or 0.0
        ),
        'baseline_latency_ms': float(getattr(baseline_result, 'latency_ms', 0.0) or 0.0),
        'candidate_latency_ms': float(getattr(candidate_result, 'latency_ms', 0.0) or 0.0),
    }


async def build_evaluation_overview(
    session: AsyncSession,
    *,
    dataset_key: str,
    experiment_group_key: str,
    baseline_run_id: str | None = None,
    candidate_run_id: str | None = None,
) -> dict[str, object]:
    dataset = await load_evaluation_dataset_by_key(session, dataset_key)
    baseline_run, candidate_run = await _resolve_run_pair(
        session,
        dataset=dataset,
        experiment_group_key=experiment_group_key,
        baseline_run_id=baseline_run_id,
        candidate_run_id=candidate_run_id,
    )

    if baseline_run is None or candidate_run is None:
        return {
            'empty': True,
            'dataset': _serialize_dataset(dataset) if dataset else None,
            'experiment_group_key': experiment_group_key,
            'baseline_run': None,
            'candidate_run': None,
            'metric_cards': {},
            'bar_chart': {'categories': [], 'baseline_series': [], 'candidate_series': []},
            'distribution_chart': {'improved': 0, 'unchanged': 0, 'regressed': 0},
            'top_improved_cases': [],
            'top_regressed_cases': [],
            'recent_cases': [],
        }

    dataset_cases = await list_evaluation_cases_by_dataset(session, baseline_run.dataset_id)
    baseline_results = _index_case_results(
        await list_evaluation_case_results_by_run(session, baseline_run.id)
    )
    candidate_results = _index_case_results(
        await list_evaluation_case_results_by_run(session, candidate_run.id)
    )
    comparisons = [
        _serialize_case_comparison(
            evaluation_case,
            baseline_results.get(evaluation_case.id),
            candidate_results.get(evaluation_case.id),
        )
        for evaluation_case in dataset_cases
    ]
    improved_cases = sorted(
        [item for item in comparisons if item['classification'] == 'improved'],
        key=lambda item: (-float(item['score_delta']), item['case_key']),
    )
    regressed_cases = sorted(
        [item for item in comparisons if item['classification'] == 'regressed'],
        key=lambda item: (float(item['score_delta']), item['case_key']),
    )
    unchanged_count = len(
        [item for item in comparisons if item['classification'] == 'unchanged']
    )

    return {
        'empty': False,
        'dataset': _serialize_dataset(dataset) if dataset else None,
        'experiment_group_key': experiment_group_key,
        'baseline_run': _serialize_run_summary(baseline_run),
        'candidate_run': _serialize_run_summary(candidate_run),
        'metric_cards': _build_metric_cards(baseline_run, candidate_run),
        'bar_chart': _build_bar_chart_payload(baseline_run, candidate_run),
        'distribution_chart': {
            'improved': len(improved_cases),
            'unchanged': unchanged_count,
            'regressed': len(regressed_cases),
        },
        'top_improved_cases': improved_cases[:3],
        'top_regressed_cases': regressed_cases[:3],
        'recent_cases': sorted(comparisons, key=lambda item: item['case_key'])[:20],
    }


async def build_evaluation_case_detail(
    session: AsyncSession,
    *,
    case_key: str,
    baseline_run_id: str,
    candidate_run_id: str,
) -> dict[str, object]:
    evaluation_case = await load_evaluation_case_by_key(session, case_key)
    if evaluation_case is None:
        raise ValueError('指定样本不存在')

    baseline_run = await load_evaluation_run_by_id(session, baseline_run_id)
    candidate_run = await load_evaluation_run_by_id(session, candidate_run_id)
    if baseline_run is None or candidate_run is None:
        raise ValueError('指定的实验运行不存在')

    baseline_result_statement: Select[tuple[AnalysisEvaluationCaseResult]] = (
        select(AnalysisEvaluationCaseResult)
        .where(AnalysisEvaluationCaseResult.run_id == baseline_run_id)
        .where(AnalysisEvaluationCaseResult.case_id == evaluation_case.id)
    )
    candidate_result_statement: Select[tuple[AnalysisEvaluationCaseResult]] = (
        select(AnalysisEvaluationCaseResult)
        .where(AnalysisEvaluationCaseResult.run_id == candidate_run_id)
        .where(AnalysisEvaluationCaseResult.case_id == evaluation_case.id)
    )
    baseline_result = (
        await session.execute(baseline_result_statement)
    ).scalar_one_or_none()
    candidate_result = (
        await session.execute(candidate_result_statement)
    ).scalar_one_or_none()

    comparison = _serialize_case_comparison(
        evaluation_case,
        baseline_result,
        candidate_result,
    )
    return {
        'case': {
            'case_key': evaluation_case.case_key,
            'ts_code': evaluation_case.ts_code,
            'topic': evaluation_case.topic,
            'anchor_event_title': evaluation_case.anchor_event_title,
            'expected_top_factor_key': evaluation_case.expected_top_factor_key,
            'notes': evaluation_case.notes,
        },
        'baseline_run': _serialize_run_summary(baseline_run),
        'candidate_run': _serialize_run_summary(candidate_run),
        'baseline_result': {
            'event_top1_hit': getattr(baseline_result, 'event_top1_hit', False),
            'factor_top1_hit': getattr(baseline_result, 'factor_top1_hit', False),
            'citation_metadata_completeness_rate': getattr(
                baseline_result,
                'citation_metadata_completeness_rate',
                0.0,
            ),
            'latency_ms': getattr(baseline_result, 'latency_ms', 0.0),
            'top_event_title': getattr(baseline_result, 'top_event_title', None),
            'top_factor_key': getattr(baseline_result, 'top_factor_key', None),
            'web_source_count': getattr(baseline_result, 'web_source_count', 0),
            'result_snapshot': getattr(baseline_result, 'result_snapshot', None),
            'case_score': comparison['baseline_score'],
            'classification': comparison['classification'],
        },
        'candidate_result': {
            'event_top1_hit': getattr(candidate_result, 'event_top1_hit', False),
            'factor_top1_hit': getattr(candidate_result, 'factor_top1_hit', False),
            'citation_metadata_completeness_rate': getattr(
                candidate_result,
                'citation_metadata_completeness_rate',
                0.0,
            ),
            'latency_ms': getattr(candidate_result, 'latency_ms', 0.0),
            'top_event_title': getattr(candidate_result, 'top_event_title', None),
            'top_factor_key': getattr(candidate_result, 'top_factor_key', None),
            'web_source_count': getattr(candidate_result, 'web_source_count', 0),
            'result_snapshot': getattr(candidate_result, 'result_snapshot', None),
            'case_score': comparison['candidate_score'],
            'classification': comparison['classification'],
        },
    }
