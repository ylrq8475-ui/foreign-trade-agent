from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ai.email_generator import EmailDraftGenerator
from config.settings import get_settings
from config.statuses import (
    DRAFT_STATUS_PENDING,
    STATUS_REPLIED,
    STATUS_REVIEW,
    STATUS_SENT,
)
from database.models import coerce_customer_profile
from database.repository import CustomerRepository


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Force-regenerate customer drafts using the current factory-customer-email-match skill."
    )
    parser.add_argument(
        "--include-sent",
        action="store_true",
        help="Also rewrite drafts for customers already marked sent or replied.",
    )
    args = parser.parse_args()

    settings = get_settings()
    repository = CustomerRepository(
        settings.db_path,
        journal_mode=settings.db_journal_mode,
        synchronous=settings.db_synchronous,
    )
    repository.init_db()
    generator = EmailDraftGenerator(settings)

    customers = repository.list_customers()
    processed: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []

    for customer in customers:
        status = str(customer.get("status") or "")
        if not args.include_sent and status in {STATUS_SENT, STATUS_REPLIED}:
            skipped.append(
                {
                    "id": customer.get("id"),
                    "company_name": customer.get("company_name"),
                    "reason": f"status={status}",
                }
            )
            continue

        profile = coerce_customer_profile(customer.get("profile_json") or customer)
        draft = generator.generate(customer, profile)
        review_note = (
            "[Skill Regenerated] Batch-regenerated using factory-customer-email-match. "
            "Please review before sending."
        )
        updates = {
            "status": STATUS_REVIEW,
            "email_subject": draft.subject,
            "email_body": draft.body,
            "email_basis": draft.personalization_basis,
            "email_ai_tone_risk": draft.ai_tone_risk,
            "draft_review_status": DRAFT_STATUS_PENDING,
            "draft_review_note": review_note,
            "approved_at": "",
            "review_required": bool(profile.review_required or draft.review_required),
        }
        repository._update_customer(int(customer["id"]), updates)
        repository._log_customer_action(
            int(customer["id"]),
            "批量重生成草稿",
            "已按当前 factory-customer-email-match skill 强制重生成草稿，需重新人工审核。",
        )
        processed.append(
            {
                "id": customer.get("id"),
                "company_name": customer.get("company_name"),
                "status_before": status,
                "subject": draft.subject,
                "body_preview": draft.body[:160],
                "basis_len": len(draft.personalization_basis or []),
                "tone_risk": draft.ai_tone_risk,
                "review_required": draft.review_required,
            }
        )

    print(
        json.dumps(
            {
                "processed_count": len(processed),
                "skipped_count": len(skipped),
                "processed": processed,
                "skipped": skipped,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
