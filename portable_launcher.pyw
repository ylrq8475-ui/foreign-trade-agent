from __future__ import annotations

import os
from pathlib import Path


def _runtime_home() -> Path:
    base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "CustomerAgent"


os.environ.setdefault("CUSTOMER_AGENT_HOME", str(_runtime_home()))
os.chdir(Path(__file__).resolve().parent)

from desktop_launcher import main


if __name__ == "__main__":
    raise SystemExit(main())
