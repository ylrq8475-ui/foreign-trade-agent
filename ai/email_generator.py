from __future__ import annotations

import re

from config.email_skill import load_email_skill_context
from config.factory_profile import (
    FACTORY_PROFILE,
    factory_context_summary,
    select_matching_strengths,
)
from config.prompts import build_email_prompt
from config.settings import Settings
from database.models import CustomerProfileResult, EmailDraftResult
from ai.minimax_client import MiniMaxClient


class EmailDraftGenerator:
    def __init__(self, settings: Settings, client: MiniMaxClient | None = None) -> None:
        self.settings = settings
        self.client = client or MiniMaxClient(settings)

    def generate(self, customer: dict, profile: CustomerProfileResult) -> EmailDraftResult:
        skill_context = load_email_skill_context()
        if not skill_context.available:
            return self._manual_review_result(
                "Email skill unavailable. Please restore factory-customer-email-match before generating outreach."
            )
        if not profile.evidence or self._evidence_low_quality(profile.evidence):
            return self._manual_review_result(
                "Information insufficient for a reliable personalized draft. Please review the website content manually."
            )

        remote_result = self._generate_with_remote_model(customer, profile, skill_context)
        if remote_result:
            return remote_result
        local_result = self._generate_local(customer, profile)
        if self._skill_compliance_issues(local_result, profile):
            return self._manual_review_result(
                "Draft could not be generated in a skill-compliant way. Please review the website content manually."
            )
        return local_result

    def _generate_with_remote_model(
        self, customer: dict, profile: CustomerProfileResult, skill_context
    ) -> EmailDraftResult | None:
        if not self.client.enabled:
            return None
        try:
            matched_strengths = self._matched_strengths(profile)
            payload = self.client.chat_json(
                system_prompt=(
                    "Return strict JSON for a short outbound B2B email draft. "
                    "The draft must connect the target customer's real website signals "
                    "with the most relevant supplier strengths only. "
                    "Write like an experienced export salesperson, not like a marketing bot. "
                    "Present us as a stable silicone kitchenware manufacturer and professional supplier, "
                    "not a factory showing off size. "
                    "If the evidence supports it, add one light market-signal sentence about "
                    "repeat-order demand, assortment extension, or channel fit. "
                    "Use concrete buyer-facing language, avoid generic praise, and avoid fluffy phrases "
                    "such as 'broad range', 'for your team', or 'for reference' unless the evidence truly supports them. "
                    "Follow the Factory Customer Email Match skill guidance when it is more specific than these generic rules.\n\n"
                    f"Factory Customer Email Match skill:\n{skill_context.skill_guidance}"
                ),
                user_prompt=build_email_prompt(
                    customer,
                    profile.to_dict(),
                    {
                        "your_company_type": self.settings.your_company_type,
                        "your_products": self.settings.your_products,
                        "your_advantage": self.settings.your_advantage,
                        "factory_summary": factory_context_summary(),
                        "matched_strengths": matched_strengths,
                        "skill_guidance": skill_context.skill_guidance,
                        "skill_company_profile": skill_context.company_profile,
                    },
                ),
            )
        except Exception as exc:  # pragma: no cover
            self.client.last_error = f"{type(exc).__name__}: {exc}"
            return None
        if not payload:
            return None
        result = EmailDraftResult(
            subject=payload.get("subject", "Quick question"),
            body=payload.get("email_body", ""),
            personalization_basis=payload.get("personalization_basis", profile.evidence[:1]),
            contains_inference=bool(payload.get("contains_inference", False)),
            ai_tone_risk=payload.get("ai_tone_risk", "medium"),
            review_required=bool(payload.get("review_required", True)),
        )
        processed = self._post_process_result(result, customer, profile)
        if self._skill_compliance_issues(processed, profile):
            fallback = self._generate_local(customer, profile)
            if self._skill_compliance_issues(fallback, profile):
                return None
            return fallback
        return processed

    def _generate_local(self, customer: dict, profile: CustomerProfileResult) -> EmailDraftResult:
        evidence = self._preferred_evidence(profile)
        company_name = self._display_company_name(customer.get("company_name", "your team"))
        matched_strengths = self._matched_strengths(profile)
        subject = self._build_subject(customer, profile, matched_strengths)
        opening_line = self._opening_line(profile, evidence)
        fit_line = self._fit_line(profile)
        support_line = self._support_line(profile, matched_strengths)
        credibility_line = self._credibility_line(profile)
        market_signal_line = self._market_signal_line(profile)
        closing_question = self._closing_question(profile)
        body = (
            f"Hello {company_name} team,\n\n"
            f"{opening_line}\n\n"
            f"{fit_line} {support_line}{credibility_line}{market_signal_line}\n\n"
            f"{closing_question}\n\n"
            f"Best regards,\n"
            f"{self.settings.your_company_name}"
        )
        tone_risk = "low" if len(body.split()) <= 110 else "medium"
        result = EmailDraftResult(
            subject=subject,
            body=body,
            personalization_basis=profile.evidence[:1],
            contains_inference=profile.contains_inference,
            ai_tone_risk=tone_risk,
            review_required=True,
        )
        return self._post_process_result(result, customer, profile)

    def _trim_quote(self, quote: str) -> str:
        trimmed = quote.strip().strip('"')
        words = trimmed.split()
        return " ".join(words[:16]) if words else "your market positioning"

    def _matched_strengths(self, profile: CustomerProfileResult) -> list[str]:
        return select_matching_strengths(
            profile.customer_type,
            profile.website_summary,
            [item.get("quote", "") for item in profile.evidence],
        )

    def _product_focus_phrase(self) -> str:
        products = FACTORY_PROFILE["core_products"][:4]
        return ", ".join(products[:-1]) + f", and {products[-1]}"

    def _opening_line(self, profile: CustomerProfileResult, evidence: dict) -> str:
        observed = self._observed_text(profile)
        evidence_text = self._evidence_text(profile)
        evidence_category = str(evidence.get("category", "general"))
        quote = self._trim_quote(evidence.get("quote", ""))
        lowered = " ".join(
            [
                profile.customer_type.lower(),
                observed,
            ]
        )
        if self._is_private_label_target(evidence_text):
            return (
                "I saw on your website that private-label work appears alongside your broader assortment."
            )
        if self._is_brand_owner_target(evidence_text):
            return (
                "I saw on your website that you present your own brand alongside a wider kitchen assortment."
            )
        if evidence_category == "company_positioning" and any(
            marker in evidence_text for marker in ("supplier", "distributor", "importer", "wholesaler")
        ):
            return (
                "I was looking through your website and saw that your business is focused on supplying kitchen and hospitality products to the market."
            )
        if evidence_category == "company_positioning" and any(
            marker in evidence_text for marker in ("vertriebsexperten", "representing", "exclusive", "deutschen markt")
        ):
            return (
                "I was looking through your website and saw that your business is focused on representing kitchen brands in the German market."
            )
        if evidence_category == "product_range":
            return (
                "I noticed your product range includes a broad selection of kitchen tools and service items."
            )
        if "hotel" in lowered or "kitchen-equipment" in lowered or "kitchen equipment" in lowered:
            return (
                "I noticed your product range includes a broad selection of kitchen tools and service items."
            )
        if "baking" in lowered or "bakery" in lowered:
            return (
                "I was looking through your site and saw a clear baking-focused assortment."
            )
        if "distributor" in lowered or "wholesaler" in lowered or "importer" in lowered:
            return (
                "I was looking through your website and saw that you work across kitchen and housewares supply."
            )
        return f"I was looking through your website and noticed that you highlight {quote}."

    def _fit_line(self, profile: CustomerProfileResult) -> str:
        observed = self._observed_text(profile)
        evidence_text = self._evidence_text(profile)
        lowered = " ".join([profile.customer_type.lower(), observed])
        if "hotel" in lowered or "kitchen-equipment" in lowered or "kitchen equipment" in lowered:
            return (
                "That seemed relevant because we are a manufacturer specializing in food-grade silicone kitchen tools and baking accessories that can sit naturally alongside a wider kitchen assortment."
            )
        if "baking" in lowered or "bakery" in lowered:
            return (
                "That seemed relevant because we are a manufacturer specializing in silicone baking tools and core kitchen utensils such as spatulas, scrapers, and brushes."
            )
        if self._is_private_label_target(evidence_text):
            return (
                "That seemed relevant because we are a manufacturer specializing in food-grade silicone kitchen tools for OEM and private-label programs."
            )
        if self._is_brand_owner_target(evidence_text):
            return (
                "That seemed relevant because we are a manufacturer specializing in food-grade silicone kitchen tools that can support assortment extension and branded programs."
            )
        return (
            f"That seemed relevant because we are a manufacturer specializing in food-grade {self._product_focus_phrase()}."
        )

    def _build_subject(
        self, customer: dict, profile: CustomerProfileResult, matched_strengths: list[str]
    ) -> str:
        observed = self._observed_text(profile)
        evidence_text = self._evidence_text(profile)
        lowered = " ".join(
            [
                profile.customer_type.lower(),
                observed,
            ]
        )
        if self._is_private_label_target(evidence_text):
            return f"OEM silicone kitchen tools for {customer.get('company_name', 'your assortment')}"
        if self._is_brand_owner_target(evidence_text):
            return "Silicone kitchen tools for your assortment"
        if "hotel" in lowered or "kitchen equipment" in lowered:
            return "Quick question about your kitchen assortment"
        if "baking" in lowered or "bakery" in lowered:
            return "Quick question about your baking range"
        if "kitchen" in lowered or "utensil" in lowered:
            return "Quick question about your kitchen assortment"
        return "Quick question about your housewares assortment"

    def _strength_sentence(self, matched_strengths: list[str]) -> str:
        if not matched_strengths:
            return self.settings.your_advantage
        first = matched_strengths[0]
        replacements = {
            "OEM/ODM support with Pantone color matching, logo printing, and private-label execution":
                "OEM/ODM support, Pantone color matching, and custom logo printing",
            "Focused supply in silicone kitchen tools, baking accessories, and daily-use kitchen items":
                "a focused range of silicone kitchen tools and baking accessories",
            "Stable export supply for channel buyers, with flexible MOQ and consistent lead-time support":
                "clear communication, stable quality, flexible MOQ, and reliable lead times",
            "Food-contact production with FDA/LFGB-compliant materials and TUV/SGS testing support":
                "FDA/LFGB-compliant materials, stable quality control, and TUV/SGS testing support",
            "Professional supply support for silicone and plastic kitchen products with OEM/ODM and export experience":
                "reliable export support for silicone and plastic kitchen products",
        }
        return replacements.get(first, first.lower())

    def _support_line(self, profile: CustomerProfileResult, matched_strengths: list[str]) -> str:
        observed = self._observed_text(profile)
        evidence_text = self._evidence_text(profile)
        lowered = " ".join([profile.customer_type.lower(), observed, evidence_text])
        if self._is_private_label_target(evidence_text):
            return (
                "On the execution side, we can support Pantone color matching, logo printing, and customer-designated materials."
            )
        if any(marker in lowered for marker in ("supplier", "distributor", "importer", "wholesaler", "hotel")) and any(
            marker in lowered for marker in ("food", "fda", "lfgb", "bakery", "gastro", "compliance")
        ):
            return (
                "On the supply side, we focus on stable quality control, workable MOQ, reliable lead times, and food-contact compliance when needed."
            )
        if any(marker in lowered for marker in ("supplier", "distributor", "importer", "wholesaler", "hotel")):
            return (
                "On the supply side, we focus on stable quality control, workable MOQ, and reliable lead times."
            )
        if any(marker in lowered for marker in ("food grade", "fda", "lfgb", "bakery", "gastro")):
            return (
                "We can also support FDA/LFGB material requirements and testing documentation when needed."
            )
        strength = self._strength_sentence(matched_strengths)
        if strength == "reliable export support for silicone and plastic kitchen products":
            return "On the cooperation side, we focus on clear communication, stable quality, and reliable export coordination."
        return f"On the cooperation side, we can support this with {strength}."

    def _credibility_line(self, profile: CustomerProfileResult) -> str:
        observed = self._observed_text(profile)
        evidence_text = self._evidence_text(profile)
        lowered = " ".join([profile.customer_type.lower(), observed])
        if self._is_private_label_target(evidence_text) or any(
            marker in lowered for marker in ("distributor", "importer", "wholesaler", "supplier")
        ):
            return " Much of our kitchen-tool work is for EU-facing distributor and brand programs."
        if self._is_brand_owner_target(evidence_text):
            return " Much of our kitchen-tool work is for brand-oriented and distributor programs across Europe."
        return ""

    def _market_signal_line(self, profile: CustomerProfileResult) -> str:
        evidence_text = self._evidence_text(profile)
        observed = self._observed_text(profile)
        lowered = " ".join([profile.customer_type.lower(), observed, evidence_text])
        if self._is_private_label_target(evidence_text):
            return (
                " That kind of positioning usually suggests room for repeat-order OEM silicone lines rather than one-off items."
            )
        if any(marker in lowered for marker in ("baking", "bakery")):
            return (
                " That kind of assortment usually points to steady reorder demand in practical silicone baking tools."
            )
        if any(marker in lowered for marker in ("distributor", "wholesaler", "importer", "supplier", "vertrieb", "handel")) and any(
            marker in lowered for marker in ("kitchen", "housewares", "utensil", "serving", "gastro", "hospitality")
        ):
            return (
                " That kind of channel-focused assortment usually points to steady repeat-order demand in dependable kitchenware lines."
            )
        if any(marker in lowered for marker in ("retail", "retailer", "brand owner", "own brand", "eigenmarke")) and any(
            marker in lowered for marker in ("kitchen", "housewares", "baking", "utensil")
        ):
            return (
                " That usually suggests there is room for dependable silicone lines that can extend an existing kitchen assortment."
            )
        return ""

    def _closing_question(self, profile: CustomerProfileResult) -> str:
        evidence_text = self._evidence_text(profile)
        observed = self._observed_text(profile)
        lowered = " ".join([profile.customer_type.lower(), observed, evidence_text])
        if self._is_private_label_target(evidence_text):
            return "If relevant on your side, would a brief overview of suitable items and customization options be useful?"
        if any(marker in lowered for marker in ("supplier", "distributor", "importer", "wholesaler", "hotel")):
            return "If useful, would it make sense for me to send a brief overview of a few silicone items that may fit your assortment?"
        if "baking" in lowered or "bakery" in lowered:
            return "If useful, would a brief baking-focused item overview be worth sending over?"
        return "If useful, would a brief overview of a few suitable items be worth sending over?"


    def _evidence_low_quality(self, evidence: list[dict]) -> bool:
        quote = str(evidence[0].get("quote", "")).lower() if evidence else ""
        html_markers = ("<!doctype", "<html", "<head", "<meta", "schema.org/webpage")
        return not quote or any(marker in quote for marker in html_markers)

    def _is_private_label_target(self, lowered: str) -> bool:
        return "private label" in lowered

    def _is_brand_owner_target(self, lowered: str) -> bool:
        return any(marker in lowered for marker in ("brand owner", "own brand", "eigenmarke"))

    def _observed_text(self, profile: CustomerProfileResult) -> str:
        return " ".join(
            [
                profile.website_summary.lower(),
                " ".join(item.get("quote", "").lower() for item in profile.evidence),
            ]
        )

    def _evidence_text(self, profile: CustomerProfileResult) -> str:
        return " ".join(item.get("quote", "").lower() for item in profile.evidence)

    def _preferred_evidence(self, profile: CustomerProfileResult) -> dict:
        noisy_markers = (
            "catalogue",
            "contact",
            "jobs",
            "menu",
            "impressum",
            "datenschutz",
            "agb",
            "website: amazon",
            "website: ebay",
            "website: otto",
            "website: kaufland",
            "website: qvc",
            "falls du eine frage",
        )
        category_priority = {
            "company_positioning": 5,
            "product_range": 4,
            "private_label": 3,
            "brand_owner": 2,
            "brand_story": 1,
            "general": 0,
        }
        ranked = sorted(
            profile.evidence,
            key=lambda item: category_priority.get(str(item.get("category", "general")), 0),
            reverse=True,
        )
        for item in ranked:
            quote = str(item.get("quote", "")).lower()
            if quote and not any(marker in quote for marker in noisy_markers):
                return item
        return profile.evidence[0]

    def _post_process_result(
        self, result: EmailDraftResult, customer: dict, profile: CustomerProfileResult
    ) -> EmailDraftResult:
        subject = self._clean_subject(result.subject, customer, profile)
        body = self._clean_body(result.body)
        word_count = len(body.split())
        tone_risk = "low" if word_count <= 110 else "medium" if word_count <= 150 else "high"
        return EmailDraftResult(
            subject=subject,
            body=body,
            personalization_basis=result.personalization_basis,
            contains_inference=result.contains_inference,
            ai_tone_risk=tone_risk,
            review_required=result.review_required or tone_risk == "high",
        )

    def _manual_review_result(self, body: str) -> EmailDraftResult:
        return EmailDraftResult(
            subject="Information insufficient for a personalized introduction",
            body=body,
            personalization_basis=[],
            contains_inference=False,
            ai_tone_risk="low",
            review_required=True,
        )

    def review_manual_draft(
        self,
        customer: dict,
        profile: CustomerProfileResult,
        *,
        subject: str,
        body: str,
        review_note: str = "",
    ) -> tuple[EmailDraftResult, str, list[str]]:
        skill_context = load_email_skill_context()
        raw_result = EmailDraftResult(
            subject=subject,
            body=body,
            personalization_basis=profile.evidence[:1],
            contains_inference=profile.contains_inference,
            ai_tone_risk="medium",
            review_required=True,
        )
        raw_issues = self._skill_compliance_issues(raw_result, profile)
        normalized = EmailDraftResult(
            subject=self._clean_subject(subject, customer, profile),
            body=self._clean_body(body),
            personalization_basis=profile.evidence[:1],
            contains_inference=profile.contains_inference,
            ai_tone_risk="medium",
            review_required=True,
        )
        normalized = self._post_process_result(normalized, customer, profile)
        issues = list(dict.fromkeys(raw_issues + self._skill_compliance_issues(normalized, profile)))
        merged_note = self._merge_review_note(
            review_note=review_note,
            skill_available=skill_context.available,
            issues=issues,
        )
        return normalized, merged_note, issues

    def _clean_subject(self, subject: str, customer: dict, profile: CustomerProfileResult) -> str:
        subject = (subject or "").strip()
        if not subject:
            return self._build_subject(customer, profile, self._matched_strengths(profile))
        subject = subject.replace("GmbH team", "team")
        if "leading manufacturer" in subject.lower():
            return self._build_subject(customer, profile, self._matched_strengths(profile))
        return subject

    def _clean_body(self, body: str) -> str:
        cleaned = body.replace("\r\n", "\n").strip()
        cleaned = cleaned.replace("Dear Sir/Madam", "Hello")
        cleaned = cleaned.replace("leading manufacturer", "supplier")
        cleaned = cleaned.replace("best price", "competitive support")
        cleaned = cleaned.replace("high quality", "stable quality")
        cleaned = cleaned.replace("factory", "supplier")
        cleaned = cleaned.replace(
            "your assortment covers a broad range of kitchen and service items",
            "your product range includes a broad selection of kitchen tools and service items",
        )
        cleaned = cleaned.replace("a broad range of", "a broad selection of")
        cleaned = re.sub(r"\s+for [A-Za-z_-]+ teams\b", "", cleaned)
        cleaned = re.sub(r"\s+for reference(?=[?.!,])", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        cleaned = cleaned.replace("  ", " ")
        paragraphs = [part.strip() for part in cleaned.split("\n\n") if part.strip()]
        return "\n\n".join(paragraphs)

    def _skill_compliance_issues(
        self, result: EmailDraftResult, profile: CustomerProfileResult
    ) -> list[str]:
        body = result.body or ""
        subject = result.subject or ""
        lowered = body.lower()
        evidence_text = self._evidence_text(profile)
        issues: list[str] = []

        if not body.strip():
            issues.append("empty_body")
        if not subject.strip():
            issues.append("empty_subject")
        if "for reference" in lowered:
            issues.append("for_reference_phrase")
        if "broad range" in lowered:
            issues.append("broad_range_phrase")
        if re.search(r"\bfor [a-z_-]+ teams\b", lowered):
            issues.append("team_label_phrase")
        if lowered.count("?") > 1:
            issues.append("too_many_questions")
        if lowered.count("factory") > 1:
            issues.append("factory_bragging")
        if "private label" in lowered and not self._is_private_label_target(evidence_text):
            issues.append("unsupported_private_label")
        if "own brand" in lowered and not self._is_brand_owner_target(evidence_text):
            issues.append("unsupported_brand_owner")
        if "repeat-order" in lowered or "repeat order" in lowered:
            signal_supported = any(
                marker in " ".join(
                    [profile.customer_type.lower(), profile.website_summary.lower(), evidence_text]
                )
                for marker in (
                    "distributor",
                    "wholesaler",
                    "importer",
                    "supplier",
                    "private label",
                    "own brand",
                    "eigenmarke",
                    "baking",
                    "bakery",
                    "kitchen",
                    "housewares",
                    "gastro",
                    "hospitality",
                    "handel",
                )
            )
            if not signal_supported:
                issues.append("unsupported_market_signal")
        word_count = len(body.split())
        if word_count > 150:
            issues.append("too_long")
        return issues

    def _merge_review_note(
        self,
        *,
        review_note: str,
        skill_available: bool,
        issues: list[str],
    ) -> str:
        cleaned_note = (review_note or "").strip()
        user_lines = [
            line for line in cleaned_note.splitlines()
            if line.strip() and not line.strip().startswith("[Skill Check]")
        ]
        system_note = ""
        if not skill_available:
            system_note = "[Skill Check] factory-customer-email-match is unavailable. Manual review required."
        elif issues:
            formatted = ", ".join(issues)
            system_note = f"[Skill Check] Needs review: {formatted}."
        else:
            system_note = "[Skill Check] Passed factory-customer-email-match review."
        merged = "\n".join(user_lines + ([system_note] if system_note else []))
        return merged.strip()
    def _display_company_name(self, company_name: str) -> str:
        cleaned = (company_name or "your team").strip()
        for suffix in (" GmbH", " GmbH & Co. KG", " Ltd.", " Co., Ltd."):
            if cleaned.endswith(suffix):
                return cleaned[: -len(suffix)].strip()
        return cleaned
