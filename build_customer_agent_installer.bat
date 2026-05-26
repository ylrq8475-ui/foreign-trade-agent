@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\windows\build_windows.ps1"
if errorlevel 1 (
  echo.
  echo PyInstaller build failed. Trying source-runtime installer fallback...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\windows\build_source_installer.ps1"
  if errorlevel 1 (
    echo.
    echo Build failed.
    pause
    exit /b 1
  )
)
echo.
echo Build completed.
echo Check dist\release\ for the latest delivery folder with installer, setup guide, and release notes.
pause
