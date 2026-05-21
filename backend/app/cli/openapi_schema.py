from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.main import app

REQUIRED_PATHS = {
    "/api/analysis/stocks/{ts_code}/research-plan",
    "/api/analysis/stocks/{ts_code}/sessions",
    "/api/analysis/sessions/{session_id}",
    "/api/admin/evaluations/datasets",
    "/api/admin/evaluations/runs",
    "/api/admin/evaluations/runs/{run_id}",
}


def build_schema() -> dict[str, object]:
    return app.openapi()


def validate_schema(schema: dict[str, object]) -> list[str]:
    paths = schema.get("paths")
    if not isinstance(paths, dict):
        return ["OpenAPI schema 缺少 paths"]
    missing_paths = sorted(path for path in REQUIRED_PATHS if path not in paths)
    return [f"OpenAPI schema 缺少路径: {path}" for path in missing_paths]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导出或校验 StockProject OpenAPI schema")
    parser.add_argument(
        "command",
        choices=["validate", "export"],
        help="validate 只校验关键路径；export 将 schema 写入文件",
    )
    parser.add_argument("--output", default="", help="export 命令的输出 JSON 文件路径")
    args = parser.parse_args(argv)

    schema = build_schema()
    errors = validate_schema(schema)
    if errors:
        for error in errors:
            print(error)
        return 1

    if args.command == "export":
        if not args.output:
            print("export 命令必须提供 --output")
            return 2
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # 关键产物：schema 快照用于前后端契约核对，避免手写类型和后端响应长期漂移。
        output_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"OpenAPI schema 已导出: {output_path}")
    else:
        print("OpenAPI schema 关键路径校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
