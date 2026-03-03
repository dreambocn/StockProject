@echo off
setlocal

set "ROOT=%~dp0"

if not exist "%ROOT%backend" (
  echo [ERROR] Missing backend directory: "%ROOT%backend"
  exit /b 1
)

if not exist "%ROOT%frontend" (
  echo [ERROR] Missing frontend directory: "%ROOT%frontend"
  exit /b 1
)

start "Backend API" /D "%ROOT%backend" cmd /k "uv run fastapi dev main.py"
start "Frontend Web" /D "%ROOT%frontend" cmd /k "npm run dev"

echo Started backend and frontend in separate terminals.
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173

endlocal
