from __future__ import annotations

import socket
import threading
import time
import traceback
import webbrowser
from pathlib import Path
from urllib.request import urlopen

from config.settings import get_settings
from web.simple_server import run_simple_server


ENV_TEMPLATE = """APP_NAME=AI Customer Agent
APP_HOST=127.0.0.1
APP_PORT=8000
API_HOST=127.0.0.1
API_PORT=8010
APP_DB_JOURNAL_MODE=WAL
APP_DB_SYNCHRONOUS=NORMAL

GOOGLE_MAPS_API_KEY=
GOOGLE_MAPS_USE_ENV_PROXY=true
GOOGLE_MAPS_PROXY_URL=

MINIMAX_API_KEY=
MINIMAX_BASE_URL=
MINIMAX_MODEL=

YOUR_COMPANY_NAME=Plastic-Dingsheng
YOUR_COMPANY_TYPE=professional supplier
YOUR_PRODUCTS=food-grade silicone and plastic kitchen tools
YOUR_ADVANTAGE=stable quality, reliable lead times, and responsive communication

EMAIL_HOST=
EMAIL_PORT=587
EMAIL_USER=
EMAIL_PASSWORD=
EMAIL_FROM=
EMAIL_FROM_NAME=Plastic-Dingsheng
EMAIL_USE_TLS=true
EMAIL_SECURITY=starttls
EMAIL_TIMEOUT_SECONDS=20
EMAIL_AUTO_SEND_ON_APPROVAL=false

ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me-admin
"""


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _ensure_runtime_files() -> tuple[Path, Path]:
    settings = get_settings()
    log_dir = settings.runtime_home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    if not settings.env_path.exists():
        settings.env_path.write_text(ENV_TEMPLATE, encoding="utf-8")
    return settings.env_path, log_dir / "launcher.log"


def _write_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def _wait_and_open(url: str, log_path: Path) -> None:
    for _ in range(40):
        try:
            with urlopen(url, timeout=2) as response:  # nosec B310
                if 200 <= response.status < 500:
                    webbrowser.open(url)
                    return
        except Exception:
            time.sleep(0.5)
    _write_log(log_path, f"Browser launch skipped because {url} never became ready.")


def main() -> int:
    env_path, log_path = _ensure_runtime_files()
    settings = get_settings()
    url = f"http://{settings.app_host}:{settings.app_port}/"
    _write_log(log_path, f"Launcher started. Runtime env: {env_path}")

    if _port_open(settings.app_host, settings.app_port):
        _write_log(log_path, f"Port {settings.app_port} already in use. Opening existing site.")
        webbrowser.open(url)
        return 0

    threading.Thread(target=_wait_and_open, args=(url, log_path), daemon=True).start()
    try:
        run_simple_server(host=settings.app_host, port=settings.app_port, settings=settings)
    except Exception:
        _write_log(log_path, traceback.format_exc())
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
