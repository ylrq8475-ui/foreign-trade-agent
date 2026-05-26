# Windows Packaging

This project can be shipped as a local Windows application that starts the workspace on `http://127.0.0.1:8000/` and opens the browser automatically.

## Important security note

Do not bundle your real paid API keys or SMTP passwords into the installer for third parties.

If a third party can run the EXE locally, they can eventually extract bundled secrets.

Safe options:

1. Ship the EXE without real secrets and let each customer configure their own keys.
2. Keep your real secrets on your own server and expose a token-protected API instead.

## What this packaging does

1. Builds a Windows desktop launcher called `CustomerAgent.exe`
2. Stores writable runtime data under `%LOCALAPPDATA%\CustomerAgent`
3. Creates a local `.env` template on first launch if one does not exist
4. Opens the local workspace in the browser automatically
5. Supports a first-run setup page for keys, admin password, and SMTP
6. Includes release notes in the delivery folder

## Build prerequisites

1. Windows
2. Python 3.11+ installed locally
3. Inno Setup 6 if you want a one-click installer EXE

## One-click build

Double-click this file from the project root:

```text
build_customer_agent_installer.bat
```

It will:

1. Create `.build-venv` automatically if needed
2. Install project dependencies
3. Install PyInstaller
4. Build `CustomerAgent.exe`
5. Build `CustomerAgentSetup.exe` if Inno Setup 6 is installed
6. If PyInstaller is blocked by Windows, automatically fall back to a source-runtime installer that still installs in one click

If isolated venv creation is unavailable on the machine, the script automatically falls back to a user-scoped build on your local Python installation.

## Build steps

```powershell
.\build_customer_agent_installer.bat
```

If Inno Setup is installed, the final installer will be created at:

```text
dist\CustomerAgentSetup.exe
```

At the same time, the script also prepares a shareable delivery folder at:

```text
dist\release\CustomerAgent-Windows-<timestamp>\
```

That folder includes the installer and a Chinese end-user setup guide.
It now also includes a Chinese release-notes file so the third party can see what changed.

The build now uses an internal staging directory and no longer depends on deleting the old
`dist\CustomerAgent\` folder first, so a locked previous build is less likely to break
the next one-click package build.

If Windows keeps blocking PyInstaller while writing `CustomerAgent.exe`, the builder now
falls back to a source-runtime installer. That fallback still produces a normal
`CustomerAgentSetup.exe`, but it installs a private Python runtime plus the app source
instead of a PyInstaller executable.

Otherwise, the unpacked PyInstaller app will be available at:

```text
dist\CustomerAgent\
```

## First-run behavior

On first launch, the app creates:

```text
%LOCALAPPDATA%\CustomerAgent\.env
%LOCALAPPDATA%\CustomerAgent\data\
%LOCALAPPDATA%\CustomerAgent\logs\
```

Edit `%LOCALAPPDATA%\CustomerAgent\.env` to add customer-specific keys and SMTP settings.
