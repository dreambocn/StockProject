from pathlib import Path

from app.services.evaluation_service import EvaluationService


def test_evaluation_service_imports_default_cases_and_runs_profile_comparison(
    tmp_path: Path,
) -> None:
    service = EvaluationService(storage_dir=tmp_path / "runs")

    datasets = service.import_default_dataset()

    assert datasets[0].dataset == "default_research_cases"
    assert datasets[0].case_count >= 8
    assert "政策驱动" in datasets[0].event_types

    run = service.run_evaluation(
        dataset="default_research_cases",
        profiles=["production_current", "evidence_first_v2"],
    )

    assert run.dataset == "default_research_cases"
    assert run.status == "success"
    assert run.summary.total_cases == datasets[0].case_count
    assert run.summary.metric_breakdown["evidence_first_v2"].evidence_coverage >= (
        run.summary.metric_breakdown["production_current"].evidence_coverage
    )
    assert run.case_results[0].case_tags
    assert run.case_results[0].metric_breakdown.citation_completeness >= 0


def test_evaluation_service_filters_runs_by_dataset_profile_and_topic(
    tmp_path: Path,
) -> None:
    service = EvaluationService(storage_dir=tmp_path / "runs")
    service.import_default_dataset()
    run = service.run_evaluation(
        dataset="default_research_cases",
        profiles=["production_current", "evidence_first_v2"],
    )

    runs = service.list_runs(
        dataset="default_research_cases",
        prompt_profile="evidence_first_v2",
        topic="政策",
    )

    assert [item.run_id for item in runs] == [run.run_id]
    assert runs[0].summary.metric_breakdown["evidence_first_v2"].failure_rate == 0
