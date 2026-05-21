from pathlib import Path

from app.cli.openapi_schema import main, validate_schema
from app.main import app


def test_openapi_schema_contains_analysis_and_evaluation_paths() -> None:
    errors = validate_schema(app.openapi())

    assert errors == []


def test_openapi_schema_cli_exports_snapshot(tmp_path: Path) -> None:
    output_path = tmp_path / "openapi.json"

    exit_code = main(["export", "--output", str(output_path)])

    assert exit_code == 0
    assert output_path.exists()
    assert "/api/admin/evaluations/runs" in output_path.read_text(encoding="utf-8")
