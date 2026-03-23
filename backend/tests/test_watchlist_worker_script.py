import subprocess
import sys
from pathlib import Path


def test_run_watchlist_worker_script_bootstraps_backend_import_path() -> None:
    backend_path = Path(__file__).resolve().parents[1]
    script_path = backend_path / "scripts" / "run_watchlist_worker.py"

    # 使用独立子进程模拟“直接执行脚本文件”的导入环境，避免 pytest 自带 pythonpath 掩盖真实问题。
    command = """
import runpy
import sys
from pathlib import Path

backend = Path.cwd().resolve()
script = backend / "scripts" / "run_watchlist_worker.py"
scripts_dir = str(script.parent.resolve())
backend_dir = str(backend)
sys.modules.pop("app", None)
sys.path = [scripts_dir] + [entry for entry in sys.path if str(Path(entry).resolve()) != backend_dir]
runpy.run_path(str(script))
print("BOOTSTRAP_OK")
"""

    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=backend_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "BOOTSTRAP_OK" in result.stdout
    assert script_path.exists()
