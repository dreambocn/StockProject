from pathlib import Path

from app.cli.evaluations import main


def test_evaluation_cli_import_run_and_summary_workflow(
    tmp_path: Path,
    capsys,
) -> None:
    storage_dir = tmp_path / "evaluation-runs"

    assert main(["import-default", "--storage-dir", str(storage_dir)]) == 0
    imported_output = capsys.readouterr().out
    assert "default_research_cases" in imported_output

    assert (
        main(
            [
                "run",
                "--dataset",
                "default_research_cases",
                "--profiles",
                "production_current,evidence_first_v2",
                "--storage-dir",
                str(storage_dir),
            ]
        )
        == 0
    )
    run_output = capsys.readouterr().out
    assert "evidence_first_v2" in run_output

    assert (
        main(
            [
                "summary",
                "--dataset",
                "default_research_cases",
                "--storage-dir",
                str(storage_dir),
            ]
        )
        == 0
    )
    summary_output = capsys.readouterr().out
    assert "引用完整率" in summary_output
