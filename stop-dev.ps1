[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$rootPath = Split-Path -Parent $PSCommandPath
$gracefulTimeoutSeconds = 8

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

function Stop-RecordedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Entry,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds,
        [switch]$ForceStop,
        [switch]$DryRunMode
    )

    $process = Get-Process -Id $Entry.Pid -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return [pscustomobject]@{
            Title = $Entry.Title
            Pid = $Entry.Pid
            Status = '已退出'
        }
    }

    if ($DryRunMode) {
        return [pscustomobject]@{
            Title = $Entry.Title
            Pid = $Entry.Pid
            Status = 'DryRun'
        }
    }

    # 优先请求窗口正常关闭，让 FastAPI / Worker 有机会执行 finally 中的连接池释放。
    $gracefulClosed = $false
    if (-not $ForceStop -and $process.MainWindowHandle -ne 0) {
        try {
            $gracefulClosed = $process.CloseMainWindow()
        }
        catch {
            $gracefulClosed = $false
        }

        if ($gracefulClosed) {
            $null = $process.WaitForExit($TimeoutSeconds * 1000)
            $process.Refresh()
            if ($process.HasExited) {
                return [pscustomobject]@{
                    Title = $Entry.Title
                    Pid = $Entry.Pid
                    Status = '已优雅关闭'
                }
            }
        }
    }

    Stop-Process -Id $Entry.Pid -Force -ErrorAction SilentlyContinue
    Wait-Process -Id $Entry.Pid -Timeout $TimeoutSeconds -ErrorAction SilentlyContinue

    $remaining = Get-Process -Id $Entry.Pid -ErrorAction SilentlyContinue
    return [pscustomobject]@{
        Title = $Entry.Title
        Pid = $Entry.Pid
        Status = if ($null -eq $remaining) { '已强制停止' } else { '停止失败' }
    }
}

$processRegistryPath = Get-ProcessRegistryPath -RootPath $rootPath
$recordedEntries = @(Read-ProcessRegistry -Path $processRegistryPath)
$liveProcesses = @(Get-LiveRecordedProcesses -Entries $recordedEntries)

if ($liveProcesses.Count -eq 0) {
    Write-Host '未发现由 start-dev.ps1 记录的运行中开发服务。' -ForegroundColor Yellow
    Write-Host ("进程记录文件：{0}" -f $processRegistryPath)
    if ((Test-Path -LiteralPath $processRegistryPath -PathType Leaf) -and (-not $DryRun)) {
        Remove-Item -LiteralPath $processRegistryPath -Force
    }
    exit 0
}

if ($DryRun) {
    Write-Host 'DryRun：检测到以下开发服务将被停止：' -ForegroundColor Cyan
    $liveProcesses |
        Select-Object Title, Pid, Command |
        Format-Table -AutoSize
    exit 0
}

$results = foreach ($entry in $liveProcesses) {
    Stop-RecordedProcess `
        -Entry $entry `
        -TimeoutSeconds $gracefulTimeoutSeconds `
        -ForceStop:$Force `
        -DryRunMode:$DryRun
}

$results | Format-Table -AutoSize

$remainingProcesses = @(Get-LiveRecordedProcesses -Entries $recordedEntries)
if ($remainingProcesses.Count -eq 0) {
    Remove-Item -LiteralPath $processRegistryPath -Force -ErrorAction SilentlyContinue
    Write-Host '开发服务已全部停止，进程记录文件已清理。' -ForegroundColor Green
}
else {
    Write-Warning ('仍有进程未停止：' + (($remainingProcesses | ForEach-Object { "{0}(PID={1})" -f $_.Title, $_.Pid }) -join ', '))
    exit 1
}
