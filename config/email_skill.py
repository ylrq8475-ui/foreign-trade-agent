from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EmailSkillContext:
    skill_name: str
    skill_guidance: str
    company_profile: str
    base_dir: Path | None = None
    available: bool = False


def _candidate_skill_dirs() -> list[Path]:
    override = os.getenv("EMAIL_SKILL_DIR", "").strip()
    if override:
        return [Path(override)]

    return [
        Path(__file__).resolve().parent.parent / "skills" / "factory-customer-email-match",
        Path.home() / ".codex" / "skills" / "factory-customer-email-match",
    ]


def load_email_skill_context() -> EmailSkillContext:
    fallback = EmailSkillContext(
        skill_name="factory-customer-email-match",
        skill_guidance="",
        company_profile="",
        base_dir=None,
        available=False,
    )

    for base_dir in _candidate_skill_dirs():
        skill_path = base_dir / "SKILL.md"
        profile_path = base_dir / "references" / "dingsheng-profile.md"
        try:
            if not skill_path.exists():
                continue
            skill_guidance = skill_path.read_text(encoding="utf-8").strip()
            company_profile = ""
            if profile_path.exists():
                company_profile = profile_path.read_text(encoding="utf-8").strip()
            return EmailSkillContext(
                skill_name=base_dir.name or fallback.skill_name,
                skill_guidance=skill_guidance,
                company_profile=company_profile,
                base_dir=base_dir,
                available=True,
            )
        except OSError:
            continue

    return fallback
