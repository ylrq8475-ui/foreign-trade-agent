from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.factory_profile import default_factory_knowledge
from config.settings import get_settings
from database.repository import CustomerRepository


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed or refresh the stored factory knowledge facts used by email generation."
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print the knowledge payload without writing it to the database.",
    )
    args = parser.parse_args()

    knowledge = default_factory_knowledge()
    if args.print_only:
        print(json.dumps(knowledge, ensure_ascii=False, indent=2))
        return 0

    settings = get_settings()
    repository = CustomerRepository(
        settings.db_path,
        journal_mode=settings.db_journal_mode,
        synchronous=settings.db_synchronous,
    )
    repository.init_db()
    saved = repository.save_factory_knowledge(knowledge)
    print(
        json.dumps(
            {
                "status": "ok",
                "db_path": str(settings.db_path),
                "last_verified": saved.get("last_verified", ""),
                "updated_at": saved.get("updated_at", ""),
                "proof_keys": sorted((saved.get("proof_points", {}) or {}).keys()),
                "operational_fact_keys": sorted((saved.get("operational_facts", {}) or {}).keys()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
