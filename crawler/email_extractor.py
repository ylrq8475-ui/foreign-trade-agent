from __future__ import annotations

import re


EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)


def extract_emails(text: str) -> list[str]:
    candidates = {match.group(0).lower() for match in EMAIL_PATTERN.finditer(text or "")}
    blocked_suffixes = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".avif")
    filtered = []
    for candidate in candidates:
        if candidate.endswith(blocked_suffixes):
            continue
        filtered.append(candidate)
    return sorted(filtered)
