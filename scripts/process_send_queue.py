from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import get_settings
from database.repository import CustomerRepository
from mail.sender import ManualSender


def main() -> int:
    settings = get_settings()
    repository = CustomerRepository(
        settings.db_path,
        journal_mode=settings.db_journal_mode,
        synchronous=settings.db_synchronous,
    )
    repository.init_db()
    sender = ManualSender(repository, settings)

    result = sender.send_approved_queue()
    print("Queue result:")
    print(f"- sent: {result['sent']}")
    print(f"- failed: {result['failed']}")
    print(f"- skipped: {result['skipped']}")
    for error in result["errors"]:
        print(f"- error: {error}")
    return 0 if result["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
