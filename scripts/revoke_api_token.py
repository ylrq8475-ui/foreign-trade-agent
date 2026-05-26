from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import get_settings
from database.repository import CustomerRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="Revoke an API token.")
    parser.add_argument("--id", required=True, type=int, help="API token id")
    args = parser.parse_args()

    settings = get_settings()
    repository = CustomerRepository(
        settings.db_path,
        journal_mode=settings.db_journal_mode,
        synchronous=settings.db_synchronous,
    )
    repository.init_db()
    repository.revoke_api_token(args.id)
    print(f"API token {args.id} revoked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
