from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import get_settings
from database.repository import CustomerRepository
from mail.sender import ManualSender, SendValidationError


def main() -> int:
    settings = get_settings()
    repository = CustomerRepository(
        settings.db_path,
        journal_mode=settings.db_journal_mode,
        synchronous=settings.db_synchronous,
    )
    repository.init_db()
    sender = ManualSender(repository, settings)
    summary = sender.status_summary()

    print("SMTP summary:")
    for key in ("configured", "host", "port", "security", "from_email", "auto_send_on_approval"):
        print(f"- {key}: {summary.get(key)}")

    if not summary.get("configured"):
        print("SMTP settings are incomplete. Fill EMAIL_* values in .env first.")
        return 1

    try:
        sender.test_connection()
    except (SendValidationError, Exception) as exc:
        print(f"SMTP test failed: {type(exc).__name__}: {exc}")
        return 2

    print("SMTP test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
