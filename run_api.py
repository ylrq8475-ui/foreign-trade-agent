from __future__ import annotations

import uvicorn
from config.settings import get_settings


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("web.app:app", host=settings.api_host, port=settings.api_port, reload=False)
