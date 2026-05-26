$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Resolve-BootstrapPython {
    $candidates = @(
        @{ FilePath = "py"; Arguments = @("-3.11", "-c", "import sys; print(sys.executable)") },
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

    return $null
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

function Remove-DirectoryRobust {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    if (-not (Test-Path $Path)) {
        return
    }

    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try {
            Remove-Item $Path -Recurse -Force -ErrorAction Stop
            return
        } catch {
            if ($attempt -eq 5) {
                throw "Could not clean $Label at $Path. Close CustomerAgent, any Explorer windows opened inside the previous build output, then run the builder again."
            }
            Start-Sleep -Milliseconds 800
        }
    }
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$venvDir = Join-Path $projectRoot ".build-venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$specPath = Join-Path $PSScriptRoot "CustomerAgent.spec"
$distDir = Join-Path $projectRoot "dist"
$packagingRootBase = Join-Path $projectRoot ".packaging-output"
$buildSessionId = Get-Date -Format "yyyyMMdd-HHmmss"
$releaseDir = Join-Path $distDir "release"
$releasePackageDir = Join-Path $releaseDir "CustomerAgent-Windows-$buildSessionId"
$requirementsPath = Join-Path $projectRoot "requirements.txt"
$installerScript = Join-Path $PSScriptRoot "CustomerAgent.iss"
$installerCompiler = Resolve-InnoSetupCompiler
$installerOutput = Join-Path $releasePackageDir "CustomerAgentSetup.exe"
$legacyInstallerOutput = Join-Path $distDir "CustomerAgentSetup.exe"
$portableDir = ""
$portableOutput = ""
$deliveryReadme = Join-Path $PSScriptRoot "THIRD_PARTY_SETUP_CN.txt"
$releaseNotes = Join-Path $PSScriptRoot "RELEASE_NOTES_CN.txt"
$keywordGuide = Join-Path $PSScriptRoot "KEYWORD_SEARCH_GUIDE_CN.txt"
$buildPython = $venvPython
$pipInstallPrefix = @()

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

$bootstrapPython = Resolve-BootstrapPython

if (-not (Test-VenvReady -PythonExe $venvPython)) {
    $venvReady = $false
    if (Test-Path $venvDir) {
        try {
            Remove-Item $venvDir -Recurse -Force
        } catch {
            Write-Host "Existing build venv could not be removed cleanly. Falling back if recreation fails."
        }
    }
    try {
        Write-Host "Creating local build virtual environment with $bootstrapPython"
        & $bootstrapPython -m venv $venvDir
        $venvReady = Test-VenvReady -PythonExe $venvPython
    } catch {
        $venvReady = $false
    }
    if (-not $venvReady) {
        Write-Host "Isolated build venv is unavailable on this machine. Falling back to user-scoped build dependencies."
        $buildPython = $bootstrapPython
        $pipInstallPrefix = @("--user")
    }
}

Write-Host "Preparing build environment..."
& $buildPython -m pip install @pipInstallPrefix --upgrade pip wheel
& $buildPython -m pip install @pipInstallPrefix -r $requirementsPath
& $buildPython -m pip install @pipInstallPrefix --upgrade pyinstaller

New-Item -ItemType Directory -Path $releasePackageDir -Force | Out-Null
Copy-Item $deliveryReadme (Join-Path $releasePackageDir "Setup-Guide-CN.txt")
Copy-Item $releaseNotes (Join-Path $releasePackageDir "Release-Notes-CN.txt")
Copy-Item $keywordGuide (Join-Path $releasePackageDir "Keyword-Search-Guide-CN.txt")
New-Item -ItemType Directory -Path $packagingRootBase -Force | Out-Null

$pyInstallerSucceeded = $false
for ($attempt = 1; $attempt -le 3; $attempt++) {
    $packagingRoot = Join-Path $packagingRootBase "$buildSessionId-attempt$attempt"
    $pyiDistDir = Join-Path $packagingRoot "dist"
    $pyiBuildDir = Join-Path $packagingRoot "build"
    $portableDir = Join-Path $pyiDistDir "CustomerAgent"
    $portableOutput = Join-Path $portableDir "CustomerAgent.exe"
    Push-Location $projectRoot
    try {
        Write-Host "Running PyInstaller (attempt $attempt/3)..."
        & $buildPython -m PyInstaller --noconfirm --clean --distpath $pyiDistDir --workpath $pyiBuildDir $specPath
        if ($LASTEXITCODE -eq 0 -and (Test-Path $portableOutput)) {
            $pyInstallerSucceeded = $true
            break
        }
    } catch {
        if ($attempt -eq 3) {
            throw
        }
        Write-Host "PyInstaller attempt $attempt failed. Waiting briefly before retrying..."
        Start-Sleep -Seconds 2
    } finally {
        Pop-Location
    }
}

if (-not $pyInstallerSucceeded -or -not (Test-Path $portableOutput)) {
    throw "PyInstaller finished but $portableOutput was not created."
}

if ($installerCompiler) {
    Write-Host "Compiling installer with Inno Setup..."
    & $installerCompiler "/DAppSourceDir=$portableDir" "/DBuildOutputDir=$releasePackageDir" $installerScript
    if (Test-Path $installerOutput) {
        Write-Host "Installer created: $installerOutput"
        try {
            Copy-Item $installerOutput $legacyInstallerOutput -Force
            Write-Host "Convenience copy updated: $legacyInstallerOutput"
        } catch {
            Write-Host "Skipped updating legacy installer path because dist is busy: $legacyInstallerOutput"
        }
        Write-Host "Release package prepared: $releasePackageDir"
    } else {
        throw "Inno Setup ran but installer output was not created."
    }
} else {
    Write-Host "Portable build created: $portableOutput"
    Copy-Item $portableDir (Join-Path $releasePackageDir "CustomerAgent") -Recurse
    Write-Host "Release package prepared without installer: $releasePackageDir"
    Write-Host "Install Inno Setup 6 if you also want CustomerAgentSetup.exe."
}
