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
    parser = argparse.ArgumentParser(description="Create an API token for third-party access.")
    parser.add_argument("--name", required=True, help="Display name for the token")
    parser.add_argument(
        "--scopes",
        default="leads:search",
        help="Comma-separated scopes, e.g. leads:search,customers:analyze",
    )
    parser.add_argument("--note", default="", help="Optional note")
    parser.add_argument("--expires-at", default="", help="Optional ISO datetime, e.g. 2026-12-31T23:59:59")
    args = parser.parse_args()

    settings = get_settings()
    repository = CustomerRepository(
        settings.db_path,
        journal_mode=settings.db_journal_mode,
        synchronous=settings.db_synchronous,
    )
    repository.init_db()

    token = repository.create_api_token(
        token_name=args.name,
        scopes=[item.strip() for item in args.scopes.split(",") if item.strip()],
        note=args.note,
        expires_at=args.expires_at,
    )

    print("API token created:")
    print(f"- id: {token['id']}")
    print(f"- name: {token['token_name']}")
    print(f"- scopes: {', '.join(token['scopes']) or '-'}")
    print(f"- prefix: {token['token_prefix']}")
    print(f"- expires_at: {token['expires_at'] or '-'}")
    print(f"- token: {token['plain_token']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
