from __future__ import annotations

import json
from typing import Any

import requests

from config.settings import Settings


class MiniMaxClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.last_error = ""

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.minimax_api_key
            and self.settings.minimax_base_url
            and self.settings.minimax_model
        )

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        if not self.enabled:
            self.last_error = "MiniMax config incomplete."
            return None

        response = requests.post(
            f"{self.settings.minimax_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.minimax_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.minimax_model,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        self.last_error = ""
        content = payload["choices"][0]["message"]["content"]
        return json.loads(content)

    def status_summary(self) -> dict[str, str | bool]:
        return {
            "configured": self.enabled,
            "base_url": self.settings.minimax_base_url,
            "model": self.settings.minimax_model,
            "last_error": self.last_error,
        }
