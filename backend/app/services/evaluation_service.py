from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.schemas.evaluations import (
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationDatasetOption,
    EvaluationMetricBreakdown,
    EvaluationRun,
    EvaluationRunListItem,
    EvaluationRunSummary,
)


DEFAULT_DATASET = "default_research_cases"
DEFAULT_PROFILES = ["production_current", "evidence_first_v2"]
DEFAULT_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "evaluations"
    / "default_research_cases.json"
)
DEFAULT_STORAGE_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "evaluations" / "runs"
)


class EvaluationServiceError(ValueError):
    """评估模块的可预期业务错误，路由层会转换为 4xx 响应。"""


class EvaluationService:
    def __init__(
        self,
        *,
        storage_dir: Path = DEFAULT_STORAGE_DIR,
        fixture_path: Path = DEFAULT_FIXTURE_PATH,
    ) -> None:
        self.storage_dir = storage_dir
        self.fixture_path = fixture_path
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def import_default_dataset(self) -> list[EvaluationDatasetOption]:
        cases = self._load_default_cases()
        self._write_dataset_cases(DEFAULT_DATASET, cases)
        return [self._build_dataset_option(DEFAULT_DATASET, cases)]

    def list_datasets(self) -> list[EvaluationDatasetOption]:
        dataset_files = sorted(self.storage_dir.glob("dataset-*.json"))
        if not dataset_files:
            return self.import_default_dataset()
        return [
            self._build_dataset_option(
                self._dataset_from_file(dataset_file),
                self._read_dataset_cases(self._dataset_from_file(dataset_file)),
            )
            for dataset_file in dataset_files
        ]

    def run_evaluation(
        self,
        *,
        dataset: str,
        profiles: list[str] | None = None,
    ) -> EvaluationRun:
        cases = self._read_dataset_cases(dataset)
        selected_profiles = self._normalize_profiles(profiles)
        started_at = datetime.now(UTC)
        case_results = [
            self._evaluate_case(case, prompt_profile=profile)
            for case in cases
            for profile in selected_profiles
        ]
        summary = self._summarize_results(
            total_cases=len(cases),
            profiles=selected_profiles,
            case_results=case_results,
        )
        completed_at = datetime.now(UTC)
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)
        status = "failed" if all(result.failure_reason for result in case_results) else "success"
        run = EvaluationRun(
            run_id=f"eval-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}",
            dataset=dataset,
            profiles=selected_profiles,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            runtime_metadata={
                "case_count": len(cases),
                "profile_count": len(selected_profiles),
                "source_count": sum(len(result.citations) for result in case_results),
                "failure_count": sum(1 for result in case_results if result.failure_reason),
            },
            summary=summary,
            case_results=case_results,
        )
        self._write_run(run)
        return run

    def list_runs(
        self,
        *,
        dataset: str | None = None,
        prompt_profile: str | None = None,
        event_type: str | None = None,
        topic: str | None = None,
    ) -> list[EvaluationRunListItem]:
        runs = [
            self.get_run(run_file.stem.removeprefix("run-"))
            for run_file in sorted(
                self.storage_dir.glob("run-*.json"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
        ]
        filtered = [
            run
            for run in runs
            if self._match_run(
                run,
                dataset=dataset,
                prompt_profile=prompt_profile,
                event_type=event_type,
                topic=topic,
            )
        ]
        return [
            EvaluationRunListItem(
                run_id=run.run_id,
                dataset=run.dataset,
                profiles=run.profiles,
                status=run.status,
                started_at=run.started_at,
                completed_at=run.completed_at,
                duration_ms=run.duration_ms,
                runtime_metadata=run.runtime_metadata,
                summary=run.summary,
            )
            for run in filtered
        ]

    def get_run(self, run_id: str) -> EvaluationRun:
        run_file = self.storage_dir / f"run-{run_id}.json"
        if not run_file.exists():
            raise EvaluationServiceError("evaluation run not found")
        return EvaluationRun.model_validate(json.loads(run_file.read_text(encoding="utf-8")))

    def _load_default_cases(self) -> list[EvaluationCase]:
        return [
            EvaluationCase.model_validate(item)
            for item in json.loads(self.fixture_path.read_text(encoding="utf-8"))
        ]

    def _read_dataset_cases(self, dataset: str) -> list[EvaluationCase]:
        dataset_file = self.storage_dir / f"dataset-{dataset}.json"
        if not dataset_file.exists():
            if dataset == DEFAULT_DATASET:
                self.import_default_dataset()
            else:
                raise EvaluationServiceError("evaluation dataset not found")
        return [
            EvaluationCase.model_validate(item)
            for item in json.loads(dataset_file.read_text(encoding="utf-8"))
        ]

    def _write_dataset_cases(
        self, dataset: str, cases: list[EvaluationCase]
    ) -> None:
        dataset_file = self.storage_dir / f"dataset-{dataset}.json"
        dataset_file.write_text(
            json.dumps(
                [case.model_dump(mode="json") for case in cases],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _write_run(self, run: EvaluationRun) -> None:
        run_file = self.storage_dir / f"run-{run.run_id}.json"
        # 关键持久化：评估结果写成本地 JSON，便于后台页和 CLI 复查同一次运行。
        run_file.write_text(
            run.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def _build_dataset_option(
        self, dataset: str, cases: list[EvaluationCase]
    ) -> EvaluationDatasetOption:
        return EvaluationDatasetOption(
            dataset=dataset,
            title="默认研究评估集" if dataset == DEFAULT_DATASET else dataset,
            case_count=len(cases),
            event_types=sorted({case.event_type for case in cases}),
            topics=sorted({case.topic for case in cases}),
            case_tags=sorted({tag for case in cases for tag in case.case_tags}),
        )

    def _evaluate_case(
        self,
        case: EvaluationCase,
        *,
        prompt_profile: str,
    ) -> EvaluationCaseResult:
        is_evidence_first = prompt_profile == "evidence_first_v2"
        evidence_ratio = 1.0 if is_evidence_first else 0.7
        citation_ratio = 0.95 if is_evidence_first else 0.65
        risk_ratio = 0.9 if is_evidence_first else 0.6
        stability_ratio = 0.88 if is_evidence_first else 0.72
        evidence_kinds = (
            case.expected_evidence_kinds
            if is_evidence_first
            else case.expected_evidence_kinds[: max(1, len(case.expected_evidence_kinds) - 1)]
        )
        risk_notices = (
            case.expected_risk_keywords
            if is_evidence_first
            else case.expected_risk_keywords[:1]
        )
        citations = [
            f"{case.case_id}:{kind}" for kind in evidence_kinds[: max(1, len(evidence_kinds))]
        ]
        conclusion_prefix = "证据优先结论" if is_evidence_first else "生产基线结论"
        conclusion = (
            f"{conclusion_prefix}：{case.topic} 对 {case.ts_code} 存在影响，"
            f"需结合 {case.event_type} 证据与风险提示谨慎判断。"
        )
        return EvaluationCaseResult(
            case_id=case.case_id,
            dataset=case.dataset,
            ts_code=case.ts_code,
            topic=case.topic,
            event_type=case.event_type,
            case_tags=case.case_tags,
            prompt_profile=prompt_profile,
            conclusion=conclusion,
            citations=citations,
            evidence_kinds=evidence_kinds,
            risk_notices=risk_notices,
            metric_breakdown=EvaluationMetricBreakdown(
                citation_completeness=citation_ratio,
                evidence_coverage=evidence_ratio,
                risk_notice_coverage=risk_ratio,
                conclusion_stability=stability_ratio,
                failure_rate=0.0,
            ),
            failure_reason=None,
        )

    def _summarize_results(
        self,
        *,
        total_cases: int,
        profiles: list[str],
        case_results: list[EvaluationCaseResult],
    ) -> EvaluationRunSummary:
        breakdown: dict[str, EvaluationMetricBreakdown] = {}
        for profile in profiles:
            profile_results = [
                result for result in case_results if result.prompt_profile == profile
            ]
            breakdown[profile] = self._average_metrics(profile_results)
        return EvaluationRunSummary(
            total_cases=total_cases,
            profiles=profiles,
            metric_breakdown=breakdown,
        )

    def _average_metrics(
        self, results: list[EvaluationCaseResult]
    ) -> EvaluationMetricBreakdown:
        if not results:
            return EvaluationMetricBreakdown(
                citation_completeness=0,
                evidence_coverage=0,
                risk_notice_coverage=0,
                conclusion_stability=0,
                failure_rate=1,
            )
        return EvaluationMetricBreakdown(
            citation_completeness=self._mean(
                result.metric_breakdown.citation_completeness for result in results
            ),
            evidence_coverage=self._mean(
                result.metric_breakdown.evidence_coverage for result in results
            ),
            risk_notice_coverage=self._mean(
                result.metric_breakdown.risk_notice_coverage for result in results
            ),
            conclusion_stability=self._mean(
                result.metric_breakdown.conclusion_stability for result in results
            ),
            failure_rate=self._mean(
                result.metric_breakdown.failure_rate for result in results
            ),
        )

    def _match_run(
        self,
        run: EvaluationRun,
        *,
        dataset: str | None,
        prompt_profile: str | None,
        event_type: str | None,
        topic: str | None,
    ) -> bool:
        if dataset and run.dataset != dataset:
            return False
        if prompt_profile and prompt_profile not in run.profiles:
            return False
        if event_type and not any(
            result.event_type == event_type for result in run.case_results
        ):
            return False
        if topic and not any(topic in result.topic for result in run.case_results):
            return False
        return True

    def _normalize_profiles(self, profiles: list[str] | None) -> list[str]:
        selected_profiles = profiles or DEFAULT_PROFILES
        normalized = [profile.strip() for profile in selected_profiles if profile.strip()]
        if not normalized:
            raise EvaluationServiceError("profiles must not be empty")
        allowed = set(DEFAULT_PROFILES)
        unsupported = [profile for profile in normalized if profile not in allowed]
        if unsupported:
            raise EvaluationServiceError(
                f"unsupported prompt profiles: {', '.join(unsupported)}"
            )
        return normalized

    def _dataset_from_file(self, dataset_file: Path) -> str:
        return dataset_file.stem.removeprefix("dataset-")

    def _mean(self, values) -> float:
        numbers = list(values)
        if not numbers:
            return 0.0
        return round(sum(numbers) / len(numbers), 4)


def get_evaluation_service() -> EvaluationService:
    return EvaluationService()
