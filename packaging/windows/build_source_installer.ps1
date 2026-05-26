$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Resolve-BootstrapPython {
    $candidates = @(
        @{ FilePath = "py"; Arguments = @("-3", "-c", "import sys; print(sys.executable)") },
        @{ FilePath = "python"; Arguments = @("-c", "import sys; print(sys.executable)") }
    )

    foreach ($candidate in $candidates) {
        try {
            $resolved = & $candidate.FilePath @($candidate.Arguments) 2>$null
            if ($LASTEXITCODE -eq 0 -and $resolved) {
                return ($resolved | Select-Object -First 1).Trim()
            }
        } catch {
        }
    }

    throw "No usable Python launcher found. Install Python 3.11+ first."
}

function Resolve-InnoSetupCompiler {
    $paths = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )

    foreach ($path in $paths) {
        if ($path -and (Test-Path $path)) {
            return $path
        }
    }

    throw "Inno Setup 6 was not found."
}

function Test-VenvReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonExe
    )

    if (-not (Test-Path $PythonExe)) {
        return $false
    }

    try {
        & $PythonExe -m pip --version *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Copy-DirectoryRobust {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [Parameter(Mandatory = $true)]
        [string]$Destination,
        [string[]]$ExcludeDirs = @(),
        [string[]]$ExcludeFiles = @()
    )

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null

    $arguments = @(
        $Source,
        $Destination,
        "/E",
        "/COPY:DAT",
        "/R:2",
        "/W:1",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/NP"
    )

    if ($ExcludeDirs.Count -gt 0) {
        $arguments += "/XD"
        $arguments += $ExcludeDirs
    }

    if ($ExcludeFiles.Count -gt 0) {
        $arguments += "/XF"
        $arguments += $ExcludeFiles
    }

    & robocopy @arguments | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "Robocopy failed while copying $Source to $Destination."
    }
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$venvDir = Join-Path $projectRoot ".build-venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$requirementsPath = Join-Path $projectRoot "requirements.txt"
$bootstrapPython = Resolve-BootstrapPython
$pythonHome = Split-Path -Parent $bootstrapPython
$installerCompiler = Resolve-InnoSetupCompiler
$installerScript = Join-Path $PSScriptRoot "CustomerAgentSource.iss"
$deliveryReadme = Join-Path $PSScriptRoot "THIRD_PARTY_SETUP_CN.txt"
$releaseNotes = Join-Path $PSScriptRoot "RELEASE_NOTES_CN.txt"
$keywordGuide = Join-Path $PSScriptRoot "KEYWORD_SEARCH_GUIDE_CN.txt"
$distDir = Join-Path $projectRoot "dist"
$releaseDir = Join-Path $distDir "release"
$buildSessionId = Get-Date -Format "yyyyMMdd-HHmmss"
$releasePackageDir = Join-Path $releaseDir "CustomerAgent-Windows-$buildSessionId"
$stagingRoot = Join-Path $projectRoot ".source-installer-output"
$stageDir = Join-Path $stagingRoot $buildSessionId
$appStageDir = Join-Path $stageDir "app"
$runtimeDir = Join-Path $appStageDir "runtime"
$runtimeSitePackagesDir = Join-Path $runtimeDir "Lib\site-packages"
$legacyInstallerOutput = Join-Path $distDir "CustomerAgentSetup.exe"
$installerOutput = Join-Path $releasePackageDir "CustomerAgentSetup.exe"

if (-not (Test-Path $requirementsPath)) {
    throw "Missing requirements.txt at $requirementsPath"
}

if (-not (Test-Path $deliveryReadme)) {
    throw "Missing delivery readme at $deliveryReadme"
}

if (-not (Test-Path $releaseNotes)) {
    throw "Missing release notes at $releaseNotes"
}

if (-not (Test-Path $keywordGuide)) {
    throw "Missing keyword guide at $keywordGuide"
}

if (-not (Test-VenvReady -PythonExe $venvPython)) {
    Write-Host "Preparing local build environment..."
    if (Test-Path $venvDir) {
        Remove-Item $venvDir -Recurse -Force
    }
    & $bootstrapPython -m venv $venvDir
    & $venvPython -m pip install --upgrade pip wheel
    & $venvPython -m pip install -r $requirementsPath
}

New-Item -ItemType Directory -Path $releasePackageDir -Force | Out-Null
New-Item -ItemType Directory -Path $appStageDir -Force | Out-Null
Copy-Item $deliveryReadme (Join-Path $releasePackageDir "Setup-Guide-CN.txt")
Copy-Item $releaseNotes (Join-Path $releasePackageDir "Release-Notes-CN.txt")
Copy-Item $keywordGuide (Join-Path $releasePackageDir "Keyword-Search-Guide-CN.txt")

Write-Host "Staging portable Python runtime..."
Copy-DirectoryRobust -Source (Join-Path $pythonHome "DLLs") -Destination (Join-Path $runtimeDir "DLLs")
Copy-DirectoryRobust `
    -Source (Join-Path $pythonHome "Lib") `
    -Destination (Join-Path $runtimeDir "Lib") `
    -ExcludeDirs @("site-packages")

$topLevelRuntimeFiles = @("python.exe", "pythonw.exe", "python3.dll")
$topLevelRuntimeFiles += (
    Get-ChildItem (Join-Path $pythonHome "python*.dll") -File | Select-Object -ExpandProperty Name
)
$topLevelRuntimeFiles += (
    Get-ChildItem (Join-Path $pythonHome "vcruntime*.dll") -File | Select-Object -ExpandProperty Name
)
$topLevelRuntimeFiles = $topLevelRuntimeFiles | Sort-Object -Unique

foreach ($fileName in $topLevelRuntimeFiles) {
    $sourcePath = Join-Path $pythonHome $fileName
    if (Test-Path $sourcePath) {
        Copy-Item $sourcePath $runtimeDir -Force
    }
}

Write-Host "Staging application dependencies..."
Copy-DirectoryRobust -Source (Join-Path $venvDir "Lib\site-packages") -Destination $runtimeSitePackagesDir

Write-Host "Staging application source..."
$appDirectories = @("ai", "config", "crawler", "database", "mail", "maps", "web")
foreach ($directoryName in $appDirectories) {
    Copy-DirectoryRobust -Source (Join-Path $projectRoot $directoryName) -Destination (Join-Path $appStageDir $directoryName)
}

$appFiles = @("desktop_launcher.py", "portable_launcher.pyw", "Readme.md")
foreach ($fileName in $appFiles) {
    Copy-Item (Join-Path $projectRoot $fileName) $appStageDir -Force
}

Write-Host "Verifying staged runtime..."
$env:CUSTOMER_AGENT_HOME = Join-Path $stageDir "runtime-home"
& (Join-Path $runtimeDir "python.exe") -c "from config.settings import get_settings; import desktop_launcher; print(get_settings().runtime_home)"
Remove-Item Env:CUSTOMER_AGENT_HOME -ErrorAction SilentlyContinue

Write-Host "Compiling installer with Inno Setup..."
& $installerCompiler "/DAppSourceDir=$appStageDir" "/DBuildOutputDir=$releasePackageDir" $installerScript

if (-not (Test-Path $installerOutput)) {
    throw "Inno Setup ran but installer output was not created."
}

Copy-Item $installerOutput $legacyInstallerOutput -Force
Write-Host "Installer created: $installerOutput"
Write-Host "Convenience copy updated: $legacyInstallerOutput"
Write-Host "Release package prepared: $releasePackageDir"
