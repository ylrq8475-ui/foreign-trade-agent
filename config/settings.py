from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

try:
    from dotenv import load_dotenv, set_key
except ImportError:  # pragma: no cover
    load_dotenv = None
    set_key = None


REPO_DIR = Path(__file__).resolve().parent.parent


def _runtime_home() -> Path:
    override = os.getenv("CUSTOMER_AGENT_HOME", "").strip()
    if override:
        return Path(override)

    if getattr(sys, "frozen", False):
        if os.name == "nt":
            base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        else:
            base = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        return base / "CustomerAgent"

    return REPO_DIR


RUNTIME_HOME = _runtime_home()
REPO_ENV_PATH = REPO_DIR / ".env"
RUNTIME_ENV_PATH = RUNTIME_HOME / ".env"

if load_dotenv:
    if REPO_ENV_PATH.exists():
        load_dotenv(REPO_ENV_PATH)
    if RUNTIME_ENV_PATH.exists() and RUNTIME_ENV_PATH != REPO_ENV_PATH:
        load_dotenv(RUNTIME_ENV_PATH, override=True)


def _stringify_env_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def save_runtime_env(updates: dict[str, object]) -> Path:
    RUNTIME_HOME.mkdir(parents=True, exist_ok=True)
    RUNTIME_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not RUNTIME_ENV_PATH.exists():
        RUNTIME_ENV_PATH.write_text("", encoding="utf-8")

    if set_key:
        for key, value in updates.items():
            set_key(
                str(RUNTIME_ENV_PATH),
                str(key),
                _stringify_env_value(value),
                quote_mode="auto",
            )
    else:  # pragma: no cover
        lines = []
        existing: dict[str, str] = {}
        if RUNTIME_ENV_PATH.exists():
            for raw_line in RUNTIME_ENV_PATH.read_text(encoding="utf-8").splitlines():
                if "=" in raw_line and not raw_line.lstrip().startswith("#"):
                    key, _, raw_value = raw_line.partition("=")
                    existing[key.strip()] = raw_value
        for key, value in updates.items():
            existing[str(key)] = _stringify_env_value(value)
        for key, value in existing.items():
            lines.append(f"{key}={value}")
        RUNTIME_ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return RUNTIME_ENV_PATH


def reload_runtime_settings() -> "Settings":
    if load_dotenv and RUNTIME_ENV_PATH.exists():
        load_dotenv(RUNTIME_ENV_PATH, override=True)
    get_settings.cache_clear()
    return get_settings()


def _data_dir() -> Path:
    return Path(os.getenv("APP_DATA_DIR", str(RUNTIME_HOME / "data")))


def _db_path() -> Path:
    return Path(os.getenv("APP_DB_PATH", str(_data_dir() / "customer_workspace.sqlite3")))


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "AI Customer Agent")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    api_host: str = os.getenv("API_HOST", "127.0.0.1")
    api_port: int = int(os.getenv("API_PORT", "8010"))
    runtime_home: Path = RUNTIME_HOME
    env_path: Path = RUNTIME_ENV_PATH
    data_dir: Path = _data_dir()
    db_path: Path = _db_path()
    db_journal_mode: str = os.getenv("APP_DB_JOURNAL_MODE", "MEMORY").strip().lower()
    db_synchronous: str = os.getenv("APP_DB_SYNCHRONOUS", "OFF").strip().lower()
    google_maps_api_key: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    google_maps_use_env_proxy: bool = (
        os.getenv("GOOGLE_MAPS_USE_ENV_PROXY", "true").lower() == "true"
    )
    google_maps_proxy_url: str = os.getenv("GOOGLE_MAPS_PROXY_URL", "")
    minimax_api_key: str = os.getenv("MINIMAX_API_KEY", "")
    minimax_base_url: str = os.getenv("MINIMAX_BASE_URL", "")
    minimax_model: str = os.getenv("MINIMAX_MODEL", "")
    your_company_name: str = os.getenv("YOUR_COMPANY_NAME", "Plastic-Dingsheng")
    your_company_type: str = os.getenv(
        "YOUR_COMPANY_TYPE",
        "food-grade silicone kitchenware manufacturer and professional supplier",
    )
    your_products: str = os.getenv(
        "YOUR_PRODUCTS", "food-grade silicone and plastic kitchen tools"
    )
    your_advantage: str = os.getenv(
        "YOUR_ADVANTAGE", "stable quality, reliable lead times, and responsive communication"
    )
    request_timeout_seconds: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "12"))
    smtp_host: str = os.getenv("EMAIL_HOST", "")
    smtp_port: int = int(os.getenv("EMAIL_PORT", "587"))
    smtp_user: str = os.getenv("EMAIL_USER", "")
    smtp_password: str = os.getenv("EMAIL_PASSWORD", "")
    smtp_from_email: str = os.getenv("EMAIL_FROM", os.getenv("EMAIL_USER", ""))
    smtp_from_name: str = os.getenv("EMAIL_FROM_NAME", os.getenv("YOUR_COMPANY_NAME", ""))
    smtp_use_tls: bool = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
    smtp_security: str = os.getenv("EMAIL_SECURITY", "starttls").strip().lower()
    smtp_timeout_seconds: int = int(os.getenv("EMAIL_TIMEOUT_SECONDS", "20"))
    smtp_auto_send_on_approval: bool = (
        os.getenv("EMAIL_AUTO_SEND_ON_APPROVAL", "false").lower() == "true"
    )
    admin_username: str = os.getenv("ADMIN_USERNAME", "admin")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "change-me-admin")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.runtime_home.mkdir(parents=True, exist_ok=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
