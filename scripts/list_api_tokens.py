from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import get_settings
from database.repository import CustomerRepository


def main() -> int:
    settings = get_settings()
    repository = CustomerRepository(
        settings.db_path,
        journal_mode=settings.db_journal_mode,
        synchronous=settings.db_synchronous,
    )
    repository.init_db()

    tokens = repository.list_api_tokens()
    if not tokens:
        print("No API tokens found.")
        return 0

    for token in tokens:
        print(
            " | ".join(
                [
                    f"id={token['id']}",
                    f"name={token['token_name']}",
                    f"status={token['status']}",
                    f"scopes={','.join(token['scopes']) or '-'}",
                    f"prefix={token['token_prefix']}",
                    f"expires_at={token['expires_at'] or '-'}",
                    f"last_used_at={token['last_used_at'] or '-'}",
                ]
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
