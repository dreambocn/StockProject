import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.analysis_evaluation_case import AnalysisEvaluationCase
from app.models.analysis_evaluation_case_result import AnalysisEvaluationCaseResult
from app.models.analysis_evaluation_dataset import AnalysisEvaluationDataset
from app.models.analysis_evaluation_run import AnalysisEvaluationRun
from app.models.stock_instrument import StockInstrument


def _build_session_maker(tmp_path):
    db_path = tmp_path / 'analysis-evaluation-script.db'
    db_url = f'sqlite+aiosqlite:///{db_path.as_posix()}'
    engine = create_async_engine(db_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _create_tables() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create_tables())
    return engine, session_maker


def test_import_analysis_evaluation_dataset_script_bootstraps_backend_import_path() -> None:
    backend_path = Path(__file__).resolve().parents[1]
    script_path = backend_path / 'scripts' / 'import_analysis_evaluation_dataset.py'

    command = """
import runpy
import sys
from pathlib import Path

backend = Path.cwd().resolve()
script = backend / "scripts" / "import_analysis_evaluation_dataset.py"
scripts_dir = str(script.parent.resolve())
backend_dir = str(backend)
sys.modules.pop("app", None)
sys.path = [scripts_dir] + [entry for entry in sys.path if str(Path(entry).resolve()) != backend_dir]
runpy.run_path(str(script))
print("BOOTSTRAP_OK")
"""

    result = subprocess.run(
        [sys.executable, '-c', command],
        cwd=backend_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert 'BOOTSTRAP_OK' in result.stdout
    assert script_path.exists()


def test_import_dataset_and_run_evaluation_happy_path(tmp_path, monkeypatch) -> None:
    engine, session_maker = _build_session_maker(tmp_path)
    dataset_path = tmp_path / 'analysis_eval_dataset.json'
    dataset_path.write_text(
        json.dumps(
            {
                'dataset_key': 'analysis_eval_dataset_v1',
                'label': '人工标注样本集 v1',
                'description': '测试导入',
                'date_from': '2026-01-01',
                'date_to': '2026-03-24',
                'cases': [
                    {
                        'case_key': 'script-case-1',
                        'ts_code': '600519.SH',
                        'topic': 'monetary_policy',
                        'anchor_event_title': '消费支持政策持续加码',
                        'expected_top_factor_key': 'policy',
                        'notes': '脚本测试样本',
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )

    async def seed_instrument() -> None:
        async with session_maker() as session:
            session.add(
                StockInstrument(
                    ts_code='600519.SH',
                    symbol='600519',
                    name='贵州茅台',
                    fullname='贵州茅台酒股份有限公司',
                    list_status='L',
                )
            )
            await session.commit()

    asyncio.run(seed_instrument())

    import_script = __import__(
        'scripts.import_analysis_evaluation_dataset',
        fromlist=['import_dataset_from_file'],
    )
    run_script = __import__(
        'scripts.run_analysis_evaluation',
        fromlist=['run_evaluation_for_dataset'],
    )

    class _FakeSessionContext:
        def __call__(self):
            return self

        async def __aenter__(self):
            self._session = session_maker()
            return await self._session.__aenter__()

        async def __aexit__(self, exc_type, exc, tb):
            return await self._session.__aexit__(exc_type, exc, tb)

    async def fake_case_input_resolver(session, evaluation_case):
        _ = session
        return {
            'instrument_name': '贵州茅台',
            'events': [
                {
                    'title': evaluation_case.anchor_event_title,
                    'published_at': '2026-03-24T09:30:00+00:00',
                    'event_type': 'policy',
                    'sentiment_label': 'positive',
                    'correlation_score': 0.91,
                }
            ],
            'factor_weights': [],
        }

    async def fake_report_generator(
        ts_code,
        instrument_name,
        events,
        factor_weights,
        *,
        session=None,
        client=None,
        use_web_search=False,
        on_delta=None,
        prompt_profile_key='production_current',
    ):
        _ = (
            ts_code,
            instrument_name,
            factor_weights,
            session,
            client,
            use_web_search,
            on_delta,
        )
        is_candidate = prompt_profile_key == 'evidence_first_v2'
        return type(
            'FakeResult',
            (),
            {
                'status': 'ready',
                'summary': f'{prompt_profile_key} 摘要',
                'risk_points': ['风险提示'],
                'factor_breakdown': [
                    {
                        'factor_key': 'policy' if is_candidate else 'news',
                        'factor_label': '政策' if is_candidate else '新闻',
                        'weight': 1.0,
                        'direction': 'positive',
                        'evidence': ['证据'],
                        'reason': '测试理由',
                    }
                ],
                'generated_at': datetime(2026, 3, 24, 10, 0, tzinfo=UTC),
                'used_web_search': is_candidate,
                'web_search_status': 'used' if is_candidate else 'disabled',
                'web_sources': [
                    {
                        'title': events[0]['title'],
                        'url': 'https://example.com/news',
                        'source': 'Example',
                        'domain': 'example.com',
                        'published_at': (
                            '2026-03-24T09:30:00+00:00' if is_candidate else None
                        ),
                    }
                ],
            },
        )()

    monkeypatch.setattr(import_script, 'SessionLocal', _FakeSessionContext())
    monkeypatch.setattr(run_script, 'SessionLocal', _FakeSessionContext())
    monkeypatch.setattr(run_script, 'build_case_analysis_input', fake_case_input_resolver)
    monkeypatch.setattr(run_script, 'generate_stock_analysis_report', fake_report_generator)

    async def run_test() -> None:
        import_summary = await import_script.import_dataset_from_file(dataset_path)
        assert import_summary['dataset_key'] == 'analysis_eval_dataset_v1'
        assert import_summary['sample_count'] == 1

        run_summary = await run_script.run_evaluation_for_dataset(
            dataset_key='analysis_eval_dataset_v1',
            experiment_group_key='prompt_profile_compare_v1',
        )
        assert run_summary['baseline_run_id']
        assert run_summary['candidate_run_id']

        async with session_maker() as session:
            datasets = (
                await session.execute(select(AnalysisEvaluationDataset))
            ).scalars().all()
            cases = (
                await session.execute(select(AnalysisEvaluationCase))
            ).scalars().all()
            runs = (
                await session.execute(select(AnalysisEvaluationRun))
            ).scalars().all()
            results = (
                await session.execute(select(AnalysisEvaluationCaseResult))
            ).scalars().all()

        assert len(datasets) == 1
        assert len(cases) == 1
        assert len(runs) == 2
        assert len(results) == 2

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())
