from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from config.statuses import DRAFT_STATUS_APPROVED, STATUS_DRAFTED
from database.models import (
    CustomerProfileResult,
    EmailDraftResult,
    Lead,
    ParsedWebsite,
    WebsiteSnapshot,
)
from database.repository import CustomerRepository


class RepositoryAnalysisPreserveTests(unittest.TestCase):
    def setUp(self) -> None:
        tests_dir = Path(__file__).resolve().parent
        self.temp_dir = Path(tempfile.mkdtemp(prefix="analysis-preserve-", dir=str(tests_dir)))
        self.db_path = self.temp_dir / "workspace.sqlite3"
        self.repository = CustomerRepository(
            self.db_path,
            journal_mode="wal",
            synchronous="normal",
        )
        try:
            self.repository.init_db()
        except sqlite3.Error as exc:
            self.skipTest(f"SQLite write is unavailable in this environment: {exc}")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_factory_knowledge_is_seeded_into_app_settings(self) -> None:
        knowledge = self.repository.get_factory_knowledge()
        self.assertEqual("2026-05-26", knowledge.get("last_verified"))
        self.assertIn("lfgb", knowledge.get("proof_points", {}))
        self.assertIn("sample_lead_time", knowledge.get("operational_facts", {}))
        self.assertEqual(
            "admin@hzhesheng.com.cn",
            knowledge.get("identity", {}).get("sales_email"),
        )

    def test_failed_reanalysis_keeps_existing_good_draft(self) -> None:
        customer_id = self.repository.upsert_lead(
            Lead(
                place_id="stock-1",
                company_name="STOCK GmbH",
                country="Germany",
                website="https://www.stock-online.de/",
            )
        )

        good_evidence = [
            {
                "page": "https://www.stock-online.de/about",
                "quote": "We distribute kitchen and hospitality products in the German market.",
                "type": "fact",
                "category": "company_positioning",
            }
        ]
        good_parsed = ParsedWebsite(
            website_summary="Distributor of kitchen and hospitality products in Germany.",
            main_products=["kitchen tools"],
            customer_type="distributor",
            personalization_points=["Distributor profile"],
            source_url="https://www.stock-online.de/about",
            source_snippet="We distribute kitchen and hospitality products in the German market.",
            confidence_score=0.84,
            language="en",
            extraction_status="success",
            review_required=True,
            evidence=good_evidence,
        )
        good_profile = CustomerProfileResult(
            customer_type="distributor",
            main_products=["kitchen tools"],
            website_summary=good_parsed.website_summary,
            potential_needs=[],
            priority="medium",
            confidence_score=0.84,
            review_required=True,
            evidence=good_evidence,
            contains_inference=False,
        )
        good_draft = EmailDraftResult(
            subject="Quick question about your kitchen assortment",
            body=(
                "Hello STOCK team,\n\n"
                "I was looking through your website and saw that you work across kitchen and housewares supply.\n\n"
                "That seemed relevant because we mainly supply food-grade silicone kitchen tools. "
                "In practice, we focus on stable quality, workable MOQ, and reliable lead times.\n\n"
                "If useful, would it make sense for me to send a brief overview?\n\n"
                "Best regards,\nPlastic-Dingsheng"
            ),
            personalization_basis=good_evidence,
            contains_inference=False,
            ai_tone_risk="low",
            review_required=True,
        )

        self.repository.save_analysis(
            customer_id,
            good_parsed,
            good_profile,
            good_draft,
            snapshot=WebsiteSnapshot(
                website="https://www.stock-online.de/",
                success=True,
                combined_text="Kitchen and hospitality supply",
            ),
            email_candidates=["info@stock-online.de"],
        )
        self.repository.approve_draft(customer_id, "approved")

        failed_parsed = ParsedWebsite(
            website_summary="Website content was captured, but the extracted text quality is too low for reliable personalization.",
            main_products=[],
            customer_type="distributor",
            personalization_points=[],
            source_url="https://www.stock-online.de/",
            source_snippet="",
            confidence_score=0.2,
            language="unknown",
            extraction_status="failed",
            review_required=True,
            evidence=[],
        )
        failed_profile = CustomerProfileResult(
            customer_type="distributor",
            main_products=[],
            website_summary=failed_parsed.website_summary,
            potential_needs=[],
            priority="low",
            confidence_score=0.2,
            review_required=True,
            evidence=[],
            contains_inference=False,
        )
        failed_draft = EmailDraftResult(
            subject="Information insufficient for a personalized introduction",
            body="Information insufficient for a reliable personalized draft. Please review the website content manually.",
            personalization_basis=[],
            contains_inference=False,
            ai_tone_risk="low",
            review_required=True,
        )

        self.repository.save_analysis(
            customer_id,
            failed_parsed,
            failed_profile,
            failed_draft,
            snapshot=WebsiteSnapshot(
                website="https://www.stock-online.de/",
                success=False,
                combined_text="",
                error="Connection reset",
            ),
            email_candidates=[],
        )

        customer = self.repository.get_customer(customer_id)
        assert customer is not None
        self.assertEqual("Quick question about your kitchen assortment", customer["email_subject"])
        self.assertIn("stable quality", customer["email_body"])
        self.assertEqual(DRAFT_STATUS_APPROVED, customer["draft_review_status"])
        self.assertEqual(STATUS_DRAFTED, customer["status"])
        self.assertEqual("failed", customer["extraction_status"])
        self.assertTrue(customer["approved_at"])


if __name__ == "__main__":
    unittest.main()
