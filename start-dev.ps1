[CmdletBinding()]
param(
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# 使用脚本自身路径作为项目根目录，避免从其他目录启动时找不到相对路径。
$rootPath = Split-Path -Parent $PSCommandPath
$backendPath = Join-Path $rootPath 'backend'
$frontendPath = Join-Path $rootPath 'frontend'
$workerScriptPath = Join-Path $backendPath 'scripts\\run_watchlist_worker.py'

function Test-RequiredPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Description,
        [ValidateSet('Container', 'Leaf')]
        [string]$PathType = 'Container'
    )

    # 在启动前先做路径校验，避免子终端打开后才发现目录或脚本缺失。
    if (-not (Test-Path -LiteralPath $Path -PathType $PathType)) {
        throw "缺少$Description：$Path"
    }
}

function New-ProcessCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title,
        [Parameter(Mandatory = $true)]
        [string]$Command
    )

    # 统一在新终端里设置窗口标题，并在失败时保留错误现场，方便本地排查。
    return @"
`$Host.UI.RawUI.WindowTitle = '$Title'
try {
    $Command
}
catch {
    Write-Error ('启动失败：' + `$_.Exception.Message)
    throw
}
"@
}

Test-RequiredPath -Path $backendPath -Description '后端目录' -PathType 'Container'
Test-RequiredPath -Path $frontendPath -Description '前端目录' -PathType 'Container'
Test-RequiredPath -Path $workerScriptPath -Description '关注 Worker 脚本' -PathType 'Leaf'

$launchItems = @(
    @{
        Title = 'Backend API'
        WorkingDirectory = $backendPath
        Command = 'uv run fastapi dev main.py'
    },
    @{
        Title = 'Watchlist Worker'
        WorkingDirectory = $backendPath
        Command = 'uv run python scripts/run_watchlist_worker.py'
    },
    @{
        Title = 'Frontend Web'
        WorkingDirectory = $frontendPath
        Command = 'npm run dev'
    }
)

if ($DryRun) {
    Write-Host 'DryRun：已通过启动前检查，计划启动以下服务：' -ForegroundColor Cyan
    foreach ($item in $launchItems) {
        Write-Host ("- {0} | 目录：{1} | 命令：{2}" -f $item.Title, $item.WorkingDirectory, $item.Command)
    }
    exit 0
}

foreach ($item in $launchItems) {
    $commandText = New-ProcessCommand -Title $item.Title -Command $item.Command
    Start-Process -FilePath 'pwsh' -WorkingDirectory $item.WorkingDirectory -ArgumentList @(
        '-NoLogo',
        '-NoExit',
        '-Command',
        $commandText
    ) | Out-Null
}

Write-Host '已在独立终端中启动开发服务。' -ForegroundColor Green
Write-Host 'Backend API:      http://127.0.0.1:8000'
Write-Host 'Watchlist Worker: 已启动后台轮询'
Write-Host 'Frontend Web:     http://127.0.0.1:5173'
