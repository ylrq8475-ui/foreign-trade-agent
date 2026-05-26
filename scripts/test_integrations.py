from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import get_settings
from maps.google_places import GooglePlacesClient


def test_google_places() -> dict[str, object]:
    settings = get_settings()
    client = GooglePlacesClient(settings)
    leads = client.search_leads("LED distributor", "Germany", 1)
    lead = leads[0] if leads else None
    return {
        "configured": bool(settings.google_maps_api_key),
        "use_env_proxy": settings.google_maps_use_env_proxy,
        "explicit_proxy_set": bool(settings.google_maps_proxy_url),
        "mode": client.last_mode,
        "last_error": client.last_error,
        "sample_fallback": bool(
            lead
            and (
                lead.place_id.startswith("sample-")
                or lead.website.endswith(".example")
            )
        ),
        "first_company": lead.company_name if lead else "",
        "first_website": lead.website if lead else "",
    }


def test_minimax() -> dict[str, object]:
    settings = get_settings()
    if not (settings.minimax_api_key and settings.minimax_base_url and settings.minimax_model):
        return {
            "configured": False,
            "status": None,
            "ok": False,
            "preview": "MiniMax config incomplete.",
        }

    try:
        response = requests.post(
            f"{settings.minimax_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.minimax_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.minimax_model,
                "messages": [
                    {"role": "system", "content": "Return short plain text only."},
                    {"role": "user", "content": "Reply with OK."},
                ],
            },
            timeout=settings.request_timeout_seconds,
        )
        payload = response.json()
        preview = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {
            "configured": True,
            "status": response.status_code,
            "ok": response.ok,
            "preview": str(preview)[:160],
        }
    except Exception as exc:  # pragma: no cover
        return {
            "configured": True,
            "status": None,
            "ok": False,
            "preview": f"{type(exc).__name__}: {exc}",
        }


if __name__ == "__main__":
    result = {
        "google_places": test_google_places(),
        "minimax": test_minimax(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
