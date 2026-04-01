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
$analysisWorkerScriptPath = Join-Path $backendPath 'scripts\\run_analysis_worker.py'
$envFilePath = Join-Path $rootPath '.env'
$envExampleFilePath = Join-Path $rootPath '.env.example'

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

function Get-EnvFileValues {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $values = @{}
    foreach ($rawLine in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith('#')) {
            continue
        }

        $separatorIndex = $line.IndexOf('=')
        if ($separatorIndex -lt 1) {
            continue
        }

        $key = $line.Substring(0, $separatorIndex).Trim()
        $value = $line.Substring($separatorIndex + 1).Trim().Trim('"')
        if (-not $key) {
            continue
        }
        $values[$key] = $value
    }

    return $values
}

function Get-ProcessRegistryPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RootPath
    )

    $bytes = [System.Text.Encoding]::UTF8.GetBytes($RootPath.ToLowerInvariant())
    $hash = [Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData($bytes)).Substring(0, 16)
    $registryDirectory = Join-Path ([System.IO.Path]::GetTempPath()) 'StockProject'
    if (-not (Test-Path -LiteralPath $registryDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $registryDirectory -Force | Out-Null
    }

    return Join-Path $registryDirectory ("dev-processes-{0}.json" -f $hash)
}

function Read-ProcessRegistry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return @()
    }

    $rawContent = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($rawContent)) {
        return @()
    }

    $decoded = ConvertFrom-Json -InputObject $rawContent
    if ($decoded -is [System.Array]) {
        return @($decoded)
    }

    return @($decoded)
}

function Get-LiveRecordedProcesses {
    param(
        [object[]]$Entries
    )

    if ($null -eq $Entries) {
        return @()
    }

    $liveProcesses = @()
    foreach ($entry in $Entries) {
        $processId = 0
        if (-not [int]::TryParse([string]$entry.pid, [ref]$processId)) {
            continue
        }

        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            continue
        }

        $liveProcesses += [pscustomobject]@{
            Title = [string]$entry.title
            Pid = $processId
            Command = [string]$entry.command
            Process = $process
        }
    }

    return $liveProcesses
}

function Test-RequiredEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Values,
        [Parameter(Mandatory = $true)]
        [string[]]$Keys
    )

    $missing = @(
        foreach ($key in $Keys) {
            if (-not $Values.ContainsKey($key) -or [string]::IsNullOrWhiteSpace([string]$Values[$key])) {
                $key
            }
        }
    )

    if ($missing.Count -gt 0) {
        throw ('缺少必要环境变量：' + ($missing -join ', '))
    }
}

Test-RequiredPath -Path $backendPath -Description '后端目录' -PathType 'Container'
Test-RequiredPath -Path $frontendPath -Description '前端目录' -PathType 'Container'
Test-RequiredPath -Path $workerScriptPath -Description '关注 Worker 脚本' -PathType 'Leaf'
Test-RequiredPath -Path $analysisWorkerScriptPath -Description '分析 Worker 脚本' -PathType 'Leaf'

# 缺少 .env 时直接给出可执行指引，避免只报“文件不存在”但不知道下一步怎么做。
if (-not (Test-Path -LiteralPath $envFilePath -PathType Leaf)) {
    if (Test-Path -LiteralPath $envExampleFilePath -PathType Leaf) {
        throw "缺少根目录 .env 文件：$envFilePath`n请先执行：Copy-Item '$envExampleFilePath' '$envFilePath'，再按需修改配置后重试。"
    }

    throw "缺少根目录 .env 文件：$envFilePath"
}

$envValues = Get-EnvFileValues -Path $envFilePath
Test-RequiredEnvValue -Values $envValues -Keys @(
    'APP_ENV',
    'DB_SCHEMA_BOOTSTRAP_MODE',
    'POSTGRES_JDBC_URL',
    'POSTGRES_USER',
    'POSTGRES_PASSWORD',
    'REDIS_JDBC_URL',
    'JWT_SECRET_KEY'
)

$appEnv = [string]$envValues['APP_ENV']
$bootstrapMode = [string]$envValues['DB_SCHEMA_BOOTSTRAP_MODE']
$processRegistryPath = Get-ProcessRegistryPath -RootPath $rootPath
$existingRecordedProcesses = @(Get-LiveRecordedProcesses -Entries @(Read-ProcessRegistry -Path $processRegistryPath))
$runningTitles = if ($existingRecordedProcesses.Count -gt 0) {
    ($existingRecordedProcesses | ForEach-Object { "{0}(PID={1})" -f $_.Title, $_.Pid }) -join ', '
}
else {
    ''
}

if ($appEnv -ne 'development') {
    throw "start-dev.ps1 仅支持开发模式启动，当前 APP_ENV=$appEnv。非开发环境请先执行迁移后按部署方式启动。"
}

if ($bootstrapMode -eq 'validate_only') {
    Write-Warning '当前 DB_SCHEMA_BOOTSTRAP_MODE=validate_only，启动前请先执行 uv run alembic upgrade head。'
}

foreach ($entry in $envValues.GetEnumerator()) {
    # 统一把根目录 .env 注入当前进程，子进程会继承这些环境变量。
    [System.Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, 'Process')
}

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
        Title = 'Analysis Worker'
        WorkingDirectory = $backendPath
        Command = 'uv run python scripts/run_analysis_worker.py'
    },
    @{
        Title = 'Frontend Web'
        WorkingDirectory = $frontendPath
        Command = 'npm run dev'
    }
)

if ($DryRun) {
    Write-Host 'DryRun：已通过启动前检查，计划启动以下服务：' -ForegroundColor Cyan
    Write-Host ("- 环境文件：{0}" -f $envFilePath)
    Write-Host ("- APP_ENV：{0}" -f $appEnv)
    Write-Host ("- DB_SCHEMA_BOOTSTRAP_MODE：{0}" -f $bootstrapMode)
    Write-Host ("- 进程记录文件：{0}" -f $processRegistryPath)
    if ($existingRecordedProcesses.Count -gt 0) {
        Write-Warning ("检测到已有开发服务仍在运行：{0}" -f $runningTitles)
        Write-Host ("- 建议先执行：pwsh -File '{0}\\stop-dev.ps1'" -f $rootPath)
    }
    foreach ($item in $launchItems) {
        Write-Host ("- {0} | 目录：{1} | 命令：{2}" -f $item.Title, $item.WorkingDirectory, $item.Command)
    }
    exit 0
}

if ($existingRecordedProcesses.Count -gt 0) {
    throw "检测到已有开发服务仍在运行：$runningTitles`n请先执行：pwsh -File '$rootPath\\stop-dev.ps1'"
}

if (Test-Path -LiteralPath $processRegistryPath -PathType Leaf) {
    Remove-Item -LiteralPath $processRegistryPath -Force
}

$launchedProcesses = @()
foreach ($item in $launchItems) {
    $commandText = New-ProcessCommand -Title $item.Title -Command $item.Command
    $process = Start-Process -FilePath 'pwsh' -WorkingDirectory $item.WorkingDirectory -ArgumentList @(
        '-NoLogo',
        '-NoExit',
        '-Command',
        $commandText
    ) -PassThru

    $launchedProcesses += [pscustomobject]@{
        title = $item.Title
        pid = $process.Id
        workingDirectory = $item.WorkingDirectory
        command = $item.Command
        startedAt = (Get-Date).ToString('o')
    }
}

$launchedProcesses | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $processRegistryPath -Encoding UTF8

Write-Host '已在独立终端中启动开发服务。' -ForegroundColor Green
Write-Host 'Backend API:      http://127.0.0.1:8000'
Write-Host 'Watchlist Worker: 已启动后台轮询'
Write-Host 'Analysis Worker:  已启动分析会话队列轮询'
Write-Host 'Frontend Web:     http://127.0.0.1:5173'
Write-Host ("进程记录文件：{0}" -f $processRegistryPath)
