from __future__ import annotations

from config.settings import get_settings
from web.simple_server import run_simple_server


if __name__ == "__main__":
    settings = get_settings()
    run_simple_server(host=settings.app_host, port=settings.app_port, settings=settings)
