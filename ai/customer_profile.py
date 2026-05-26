from __future__ import annotations

from ai.minimax_client import MiniMaxClient
from config.prompts import build_profile_prompt
from config.settings import Settings
from database.models import CustomerProfileResult, ParsedWebsite


class CustomerProfileGenerator:
    def __init__(self, settings: Settings, client: MiniMaxClient | None = None) -> None:
        self.settings = settings
        self.client = client or MiniMaxClient(settings)

    def generate(self, customer: dict, parsed_site: ParsedWebsite) -> CustomerProfileResult:
        remote_result = self._generate_with_remote_model(customer, parsed_site)
        if remote_result:
            return remote_result
        return self._generate_local(customer, parsed_site)

    def _generate_with_remote_model(
        self, customer: dict, parsed_site: ParsedWebsite
    ) -> CustomerProfileResult | None:
        if not self.client.enabled:
            return None
        try:
            payload = self.client.chat_json(
                system_prompt="Return strict JSON for a B2B customer profile.",
                user_prompt=build_profile_prompt(customer, parsed_site.website_summary),
            )
        except Exception as exc:  # pragma: no cover
            self.client.last_error = f"{type(exc).__name__}: {exc}"
            return None
        if not payload:
            return None
        return CustomerProfileResult(
            customer_type=payload.get("customer_type", parsed_site.customer_type),
            main_products=payload.get("main_products", parsed_site.main_products),
            website_summary=payload.get("website_summary", parsed_site.website_summary),
            potential_needs=payload.get("potential_needs", []),
            priority=payload.get("priority", "medium"),
            confidence_score=float(
                payload.get("confidence_score", parsed_site.confidence_score)
            ),
            review_required=bool(payload.get("review_required", True)),
            evidence=payload.get("evidence", parsed_site.evidence),
            contains_inference=bool(payload.get("contains_inference", True)),
        )

    def _generate_local(
        self, customer: dict, parsed_site: ParsedWebsite
    ) -> CustomerProfileResult:
        manual_note = str(customer.get("manual_research_note", "")).strip().lower()
        customer_type = parsed_site.customer_type or customer.get("industry") or "b2b buyer"
        if manual_note:
            if any(marker in manual_note for marker in ("distributor", "wholesaler", "importer", "supplier")):
                for marker in ("distributor", "wholesaler", "importer", "supplier"):
                    if marker in manual_note:
                        customer_type = marker
                        break
            elif "brand" in manual_note:
                customer_type = "brand owner"
        main_products = parsed_site.main_products
        if not main_products and manual_note:
            hints = []
            for marker in ("spatula", "scraper", "brush", "baking", "kitchen tools", "housewares"):
                if marker in manual_note:
                    hints.append(marker)
            main_products = hints[:3]
        potential_needs = self._potential_needs(customer_type, main_products)
        confidence = parsed_site.confidence_score
        priority = (
            "high"
            if confidence >= 0.75 and main_products
            else "medium"
            if confidence >= 0.55
            else "low"
        )
        return CustomerProfileResult(
            customer_type=customer_type,
            main_products=main_products,
            website_summary=(
                f"{parsed_site.website_summary} Manual note: {customer.get('manual_research_note', '').strip()}".strip()
                if customer.get("manual_research_note")
                else parsed_site.website_summary
            ),
            potential_needs=potential_needs,
            priority=priority,
            confidence_score=confidence,
            review_required=parsed_site.review_required,
            evidence=parsed_site.evidence,
            contains_inference=bool(potential_needs),
        )

    def _potential_needs(self, customer_type: str, products: list[str]) -> list[str]:
        needs: list[str] = []
        lowered = customer_type.lower()
        if "distributor" in lowered or "wholesaler" in lowered:
            needs.extend(["stable supply", "flexible MOQ", "OEM/private label support"])
        if "importer" in lowered:
            needs.extend(["reliable export documentation", "consistent lead time"])
        if products:
            needs.append(f"additional sourcing options around {products[0]}")
        return needs[:3]
