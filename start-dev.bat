@echo off
setlocal

set "ROOT=%~dp0"

if not exist "%ROOT%backend" (
  echo [错误] 缺少后端目录："%ROOT%backend"
  exit /b 1
)

if not exist "%ROOT%frontend" (
  echo [错误] 缺少前端目录："%ROOT%frontend"
  exit /b 1
)

if not exist "%ROOT%backend\scripts\run_watchlist_worker.py" (
  echo [错误] 缺少关注 Worker 脚本："%ROOT%backend\scripts\run_watchlist_worker.py"
  exit /b 1
)

start "Backend API" /D "%ROOT%backend" cmd /k "uv run fastapi dev main.py"
start "Watchlist Worker" /D "%ROOT%backend" cmd /k "uv run python scripts/run_watchlist_worker.py"
start "Frontend Web" /D "%ROOT%frontend" cmd /k "npm run dev"

echo 已在独立终端中启动开发服务。
echo Backend API:      http://127.0.0.1:8000
echo Watchlist Worker: 已启动后台轮询
echo Frontend Web:     http://127.0.0.1:5173

endlocal
