@echo off
setlocal

set "ROOT=%~dp0"
set "SCRIPT=%ROOT%start-dev.ps1"

if not exist "%SCRIPT%" (
  echo [ERROR] Missing startup script: "%SCRIPT%"
  exit /b 1
)

pwsh -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
exit /b %ERRORLEVEL%
