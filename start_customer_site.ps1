$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$port = 8000
$url = "http://127.0.0.1:$port/"

function Get-ListenerProcess {
    try {
        $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop | Select-Object -First 1
    } catch {
        return $null
    }
    if (-not $conn) {
        return $null
    }
    return Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $conn.OwningProcess)
}

$existing = Get-ListenerProcess
if ($existing) {
    $commandLine = [string]$existing.CommandLine
    if ($commandLine -match "main\.py") {
        Stop-Process -Id $existing.ProcessId -Force -ErrorAction Stop
        Start-Sleep -Seconds 1
    } else {
        throw "Port $port is already in use by another process: $commandLine"
    }
}

Start-Process -FilePath python -ArgumentList "main.py" -WorkingDirectory $scriptDir -WindowStyle Hidden

$ready = $false
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
    }
}

if (-not $ready) {
    throw "Customer site did not become ready at $url"
}

Start-Process $url
Write-Output "Customer site is running at $url"
