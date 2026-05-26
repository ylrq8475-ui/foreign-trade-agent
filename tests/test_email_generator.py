from __future__ import annotations

import os
import shutil
import unittest
from unittest.mock import patch

from ai.email_generator import EmailDraftGenerator
from config.settings import Settings
from database.models import CustomerProfileResult


class FakeMiniMaxClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.enabled = True
        self.system_prompt = ""
        self.user_prompt = ""

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return self.payload


class EmailDraftGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(
            minimax_api_key="",
            minimax_base_url="",
            minimax_model="",
            your_company_name="Plastic-Dingsheng",
        )
        self.generator = EmailDraftGenerator(self.settings)

    def test_distributor_draft_uses_buyer_facing_language(self) -> None:
        customer = {"company_name": "STOCK GmbH"}
        profile = CustomerProfileResult(
            customer_type="distributor",
            main_products=["kitchen tools"],
            website_summary="German distributor of kitchen and hospitality products.",
            potential_needs=[],
            priority="medium",
            confidence_score=0.82,
            review_required=True,
            evidence=[
                {
                    "page": "https://example.com/about",
                    "quote": "We distribute kitchen and hospitality products in the German market.",
                    "type": "fact",
                    "category": "company_positioning",
                }
            ],
            contains_inference=False,
        )

        draft = self.generator.generate(customer, profile)

        self.assertIn("manufacturer specializing", draft.body)
        self.assertIn("stable quality control", draft.body)
        self.assertIn("reliable lead times", draft.body)
        self.assertIn("repeat-order demand", draft.body)
        self.assertIn("Plastic-Dingsheng", draft.body)
        self.assertNotIn("for distributor teams", draft.body)
        self.assertNotIn("for reference", draft.body)

    def test_private_label_angle_requires_supported_evidence(self) -> None:
        customer = {"company_name": "Example Brand"}
        profile = CustomerProfileResult(
            customer_type="brand owner",
            main_products=["kitchen tools"],
            website_summary="Own-brand kitchen assortment.",
            potential_needs=[],
            priority="medium",
            confidence_score=0.8,
            review_required=True,
            evidence=[
                {
                    "page": "https://example.com/private-label",
                    "quote": "We also support private label development for selected product lines.",
                    "type": "fact",
                    "category": "private_label",
                }
            ],
            contains_inference=False,
        )

        draft = self.generator.generate(customer, profile)

        self.assertIn("private-label", draft.body.lower())
        self.assertIn("Pantone color matching", draft.body)

    def test_missing_evidence_returns_manual_review_placeholder(self) -> None:
        customer = {"company_name": "No Evidence GmbH"}
        profile = CustomerProfileResult(
            customer_type="store",
            main_products=[],
            website_summary="",
            potential_needs=[],
            priority="low",
            confidence_score=0.1,
            review_required=True,
            evidence=[],
            contains_inference=False,
        )

        draft = self.generator.generate(customer, profile)

        self.assertIn("Information insufficient", draft.subject)
        self.assertIn("Please review the website content manually", draft.body)

    def test_product_range_opening_uses_skill_style_wording(self) -> None:
        customer = {"company_name": "Intergastro Handels"}
        profile = CustomerProfileResult(
            customer_type="wholesaler",
            main_products=["kitchen tools", "service items"],
            website_summary="Kitchen and service assortment for hospitality buyers.",
            potential_needs=[],
            priority="medium",
            confidence_score=0.74,
            review_required=True,
            evidence=[
                {
                    "page": "https://example.com/products",
                    "quote": "Kitchen tools and service items for professional buyers.",
                    "type": "fact",
                    "category": "product_range",
                }
            ],
            contains_inference=False,
        )

        draft = self.generator.generate(customer, profile)

        self.assertIn(
            "I noticed your product range includes a broad selection of kitchen tools and service items.",
            draft.body,
        )
        self.assertNotIn("broad range", draft.body)
        self.assertNotIn("for reference", draft.body)

    def test_remote_prompt_includes_skill_guidance_and_sanitizes_output(self) -> None:
        fake_client = FakeMiniMaxClient(
            {
                "subject": "Quick question about your kitchen assortment",
                "email_body": (
                    "Hi Intergastro Handels team,\n\n"
                    "I noticed your assortment covers a broad range of kitchen and service items.\n\n"
                    "We supply food-grade silicone spatulas, silicone scrapers, silicone brushes, and baking tools "
                    "for wholesaler teams. Our focus is on clear communication, stable quality, flexible MOQ, and reliable lead times.\n\n"
                    "Would it be useful if I shared a short product overview for reference?\n\n"
                    "Best regards,\n"
                    "Your Company"
                ),
                "personalization_basis": [
                    {
                        "page": "https://example.com/products",
                        "quote": "Kitchen tools and service items for professional buyers.",
                        "type": "fact",
                        "category": "product_range",
                    }
                ],
                "contains_inference": False,
                "ai_tone_risk": "medium",
                "review_required": True,
            }
        )
        generator = EmailDraftGenerator(self.settings, client=fake_client)
        customer = {"company_name": "Intergastro Handels"}
        profile = CustomerProfileResult(
            customer_type="wholesaler",
            main_products=["kitchen tools"],
            website_summary="Wholesaler of kitchen and service items.",
            potential_needs=[],
            priority="medium",
            confidence_score=0.78,
            review_required=True,
            evidence=[
                {
                    "page": "https://example.com/products",
                    "quote": "Kitchen tools and service items for professional buyers.",
                    "type": "fact",
                    "category": "product_range",
                }
            ],
            contains_inference=False,
        )

        draft = generator.generate(customer, profile)

        self.assertIn("Factory Customer Email Match skill", fake_client.system_prompt)
        self.assertIn("Factory Customer Email Match skill guidance", fake_client.user_prompt)
        self.assertNotIn("broad range", draft.body)
        self.assertNotIn("for wholesaler teams", draft.body)
        self.assertNotIn("for reference", draft.body)

    def test_missing_skill_blocks_generation_with_manual_review(self) -> None:
        customer = {"company_name": "Intergastro Handels"}
        profile = CustomerProfileResult(
            customer_type="wholesaler",
            main_products=["kitchen tools"],
            website_summary="Wholesaler of kitchen and service items.",
            potential_needs=[],
            priority="medium",
            confidence_score=0.78,
            review_required=True,
            evidence=[
                {
                    "page": "https://example.com/products",
                    "quote": "Kitchen tools and service items for professional buyers.",
                    "type": "fact",
                    "category": "product_range",
                }
            ],
            contains_inference=False,
        )

        with patch.dict(os.environ, {"EMAIL_SKILL_DIR": r"Z:\missing-skill-dir"}, clear=False):
            draft = self.generator.generate(customer, profile)

        self.assertIn("Email skill unavailable", draft.body)
        self.assertTrue(draft.review_required)

    def test_generator_reloads_skill_directory_between_runs(self) -> None:
        customer = {"company_name": "Intergastro Handels"}
        profile = CustomerProfileResult(
            customer_type="wholesaler",
            main_products=["kitchen tools"],
            website_summary="Wholesaler of kitchen and service items.",
            potential_needs=[],
            priority="medium",
            confidence_score=0.78,
            review_required=True,
            evidence=[
                {
                    "page": "https://example.com/products",
                    "quote": "Kitchen tools and service items for professional buyers.",
                    "type": "fact",
                    "category": "product_range",
                }
            ],
            contains_inference=False,
        )

        first_dir = os.path.join("tests", "_tmp_skill_fixture_one")
        second_dir = os.path.join("tests", "_tmp_skill_fixture_two")
        try:
            self._write_skill_fixture(first_dir, "Skill version one")
            self._write_skill_fixture(second_dir, "Skill version two")

            first_client = FakeMiniMaxClient(
                {
                    "subject": "Quick question about your kitchen assortment",
                    "email_body": "Hello Intergastro team,\n\nIf useful, would a brief overview be worth sending over?\n\nBest regards,\nPlastic-Dingsheng",
                    "personalization_basis": profile.evidence,
                    "contains_inference": False,
                    "ai_tone_risk": "medium",
                    "review_required": True,
                }
            )
            generator = EmailDraftGenerator(self.settings, client=first_client)

            with patch.dict(os.environ, {"EMAIL_SKILL_DIR": first_dir}, clear=False):
                generator.generate(customer, profile)
            self.assertIn("Skill version one", first_client.system_prompt)

            second_client = FakeMiniMaxClient(
                {
                    "subject": "Quick question about your kitchen assortment",
                    "email_body": "Hello Intergastro team,\n\nIf useful, would a brief overview be worth sending over?\n\nBest regards,\nPlastic-Dingsheng",
                    "personalization_basis": profile.evidence,
                    "contains_inference": False,
                    "ai_tone_risk": "medium",
                    "review_required": True,
                }
            )
            generator.client = second_client

            with patch.dict(os.environ, {"EMAIL_SKILL_DIR": second_dir}, clear=False):
                generator.generate(customer, profile)
            self.assertIn("Skill version two", second_client.system_prompt)
        finally:
            shutil.rmtree(first_dir, ignore_errors=True)
            shutil.rmtree(second_dir, ignore_errors=True)

    def test_review_manual_draft_appends_skill_pass_note(self) -> None:
        customer = {"company_name": "Intergastro Handels"}
        profile = CustomerProfileResult(
            customer_type="wholesaler",
            main_products=["kitchen tools"],
            website_summary="Wholesaler of kitchen and service items.",
            potential_needs=[],
            priority="medium",
            confidence_score=0.78,
            review_required=True,
            evidence=[
                {
                    "page": "https://example.com/products",
                    "quote": "Kitchen tools and service items for professional buyers.",
                    "type": "fact",
                    "category": "product_range",
                }
            ],
            contains_inference=False,
        )

        reviewed_draft, merged_note, issues = self.generator.review_manual_draft(
            customer,
            profile,
            subject="Quick question about your kitchen assortment",
            body=(
                "Hello Intergastro Handels team,\n\n"
                "I noticed your product range includes a broad selection of kitchen tools and service items.\n\n"
                "We are a manufacturer specializing in food-grade silicone kitchen tools. "
                "On the supply side, we focus on stable quality control, workable MOQ, and reliable lead times.\n\n"
                "If useful, would it make sense for me to send a brief overview of a few silicone items that may fit your assortment?\n\n"
                "Best regards,\nPlastic-Dingsheng"
            ),
            review_note="Checked by sales",
        )

        self.assertEqual([], issues)
        self.assertIn("[Skill Check] Passed factory-customer-email-match review.", merged_note)
        self.assertIn("Checked by sales", merged_note)
        self.assertEqual("Quick question about your kitchen assortment", reviewed_draft.subject)

    def test_review_manual_draft_flags_skill_violations(self) -> None:
        customer = {"company_name": "Intergastro Handels"}
        profile = CustomerProfileResult(
            customer_type="wholesaler",
            main_products=["kitchen tools"],
            website_summary="Wholesaler of kitchen and service items.",
            potential_needs=[],
            priority="medium",
            confidence_score=0.78,
            review_required=True,
            evidence=[
                {
                    "page": "https://example.com/products",
                    "quote": "Kitchen tools and service items for professional buyers.",
                    "type": "fact",
                    "category": "product_range",
                }
            ],
            contains_inference=False,
        )

        reviewed_draft, merged_note, issues = self.generator.review_manual_draft(
            customer,
            profile,
            subject="Quick question",
            body=(
                "Hi Intergastro Handels team,\n\n"
                "I noticed your assortment covers a broad range of kitchen and service items.\n\n"
                "We supply food-grade silicone spatulas for wholesaler teams.\n\n"
                "Would it be useful if I shared a short product overview for reference?\n\n"
                "Best regards,\nYour Company"
            ),
            review_note="",
        )

        self.assertIn("broad_range_phrase", issues)
        self.assertIn("for_reference_phrase", issues)
        self.assertIn("team_label_phrase", issues)
        self.assertIn("[Skill Check] Needs review:", merged_note)
        self.assertNotIn("broad range", reviewed_draft.body)

    def _write_skill_fixture(self, base_dir: str, skill_text: str) -> None:
        references_dir = os.path.join(base_dir, "references")
        os.makedirs(references_dir, exist_ok=True)
        with open(os.path.join(base_dir, "SKILL.md"), "w", encoding="utf-8") as skill_file:
            skill_file.write(skill_text)
        with open(
            os.path.join(references_dir, "dingsheng-profile.md"),
            "w",
            encoding="utf-8",
        ) as profile_file:
            profile_file.write("Dingsheng profile fixture")


if __name__ == "__main__":
    unittest.main()
