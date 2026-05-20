from __future__ import annotations

import argparse
from pathlib import Path

from app.services.evaluation_service import (
    DEFAULT_DATASET,
    DEFAULT_PROFILES,
    EvaluationService,
    EvaluationServiceError,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI 研究评估集命令行工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import-default", help="导入默认研究评估集")
    import_parser.add_argument(
        "--storage-dir",
        default=None,
        help="评估运行结果目录，默认使用 backend/data/evaluations/runs",
    )

    run_parser = subparsers.add_parser("run", help="运行评估集")
    run_parser.add_argument("--dataset", default=DEFAULT_DATASET)
    run_parser.add_argument("--profiles", default=",".join(DEFAULT_PROFILES))
    run_parser.add_argument(
        "--storage-dir",
        default=None,
        help="评估运行结果目录，默认使用 backend/data/evaluations/runs",
    )

    summary_parser = subparsers.add_parser("summary", help="查看评估运行摘要")
    summary_parser.add_argument("--dataset", default=DEFAULT_DATASET)
    summary_parser.add_argument(
        "--storage-dir",
        default=None,
        help="评估运行结果目录，默认使用 backend/data/evaluations/runs",
    )
    return parser


def _service_from_args(args: argparse.Namespace) -> EvaluationService:
    if args.storage_dir:
        return EvaluationService(storage_dir=Path(args.storage_dir))
    return EvaluationService()


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    service = _service_from_args(args)
    try:
        if args.command == "import-default":
            datasets = service.import_default_dataset()
            for dataset in datasets:
                print(f"已导入 {dataset.dataset}，共 {dataset.case_count} 条案例")
            return 0
        if args.command == "run":
            # 关键流程：profile 通过逗号传入，保持 PowerShell 下调用简单可读。
            profiles = [profile.strip() for profile in args.profiles.split(",")]
            run = service.run_evaluation(dataset=args.dataset, profiles=profiles)
            print(f"评估运行完成：{run.run_id}")
            print(f"数据集：{run.dataset}")
            print(f"Prompt Profiles：{', '.join(run.profiles)}")
            return 0
        if args.command == "summary":
            runs = service.list_runs(dataset=args.dataset)
            if not runs:
                print("暂无评估运行记录")
                return 0
            latest = runs[0]
            print(f"最新运行：{latest.run_id}")
            for profile, metrics in latest.summary.metric_breakdown.items():
                print(
                    f"{profile} 引用完整率={metrics.citation_completeness:.2f} "
                    f"证据覆盖率={metrics.evidence_coverage:.2f} "
                    f"风险提示覆盖率={metrics.risk_notice_coverage:.2f} "
                    f"结论稳定性={metrics.conclusion_stability:.2f} "
                    f"失败率={metrics.failure_rate:.2f}"
                )
            return 0
    except EvaluationServiceError as exc:
        print(f"评估命令失败：{exc}")
        return 2
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
