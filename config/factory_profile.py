from __future__ import annotations

from copy import deepcopy
from typing import Any


FACTORY_PROFILE = {
    "company_name": "Dingsheng Plastic & Silicone Co., Ltd.",
    "brand_name": "DINGSHENG",
    "company_type": "food-grade silicone kitchenware manufacturer and professional supplier",
    "core_products": [
        "silicone spatulas",
        "silicone scrapers",
        "silicone brushes",
        "baking tools",
        "silicone kitchen tools",
        "collapsible silicone products",
        "selected plastic kitchenware",
    ],
    "core_capabilities": [
        "OEM and ODM development",
        "food-grade silicone and plastic production",
        "customer-designated material brands accepted",
        "in-house material mixing, adjusting, and cutting",
        "one-piece silicone product design support",
        "silicone overmold with nylon, wood, or metal component support",
    ],
    "credibility_points": [
        "manufacturing since 2003",
        "6500 m2 factory in Huizhou",
        "100+ operators with 3 engineers and 5 QC operators",
        "LFGB and FDA food-contact compliance support",
        "ISO 9001-certified quality system",
        "export experience across Europe, the USA, Australia, and Japan",
        "10 silicone compression presses and 10 plastic injection machines",
        "sample tooling typically 7-14 days",
    ],
    "customer_examples": [
        "Sea to Summit",
        "Walmart",
        "Woll",
        "Kaiser",
        "OXO",
        "Tovolo",
        "Ototo",
    ],
}


DEFAULT_FACTORY_KNOWLEDGE: dict[str, Any] = {
    "source": "dingsheng_public_website",
    "last_verified": "2026-05-26",
    "identity": {
        "company_name": "Dingsheng Plastic & Silicone Co., Ltd.",
        "brand_name": "DINGSHENG",
        "company_type": "food-grade silicone kitchenware manufacturer and professional supplier",
        "established": "2003",
        "facility": "6,500 m2 factory",
        "team": "100+ operators, 3 engineers, 5 QC operators",
        "phone_whatsapp": "+86 150 1809 1819",
        "telephone": "+86 752 381 2369",
        "sales_email": "admin@hzhesheng.com.cn",
        "compliance_email": "qc@hzhesheng.com.cn",
        "hours": "Mon-Sat 09:00-18:00 CST",
        "response_time": "< 1 hour during CST business hours",
    },
    "proof_points": {
        "lfgb": {
            "label": "LFGB §30 / §31",
            "email_phrase": "LFGB food-contact testing",
            "value": "Certified / tested 2025",
            "usage": "Prioritize for Germany, EU kitchenware, and food-contact first-touch emails.",
            "source_pages": ["certificates.html", "quality.html", "index.html"],
        },
        "fda": {
            "label": "FDA 21 CFR 177.2600",
            "email_phrase": "FDA food-contact testing",
            "value": "Certified / tested 2025",
            "usage": "Use as a supporting proof point in first-touch kitchenware emails.",
            "source_pages": ["certificates.html", "quality.html", "index.html"],
        },
        "iso9001": {
            "label": "ISO 9001:2015",
            "email_phrase": "an ISO 9001-certified quality system",
            "value": "Current",
            "usage": "Use when a buyer cares about quality-system discipline or supplier approval.",
            "source_pages": ["certificates.html", "quality.html", "index.html", "about.html"],
        },
        "bsci": {
            "label": "BSCI",
            "email_phrase": "BSCI audit support",
            "value": "Audit-ready / certificate on file",
            "usage": "Use for retail, brand, distributor, or audit-sensitive buyers when concise.",
            "source_pages": ["certificates.html", "quality.html"],
        },
        "smeta": {
            "label": "SMETA",
            "email_phrase": "SMETA audit support",
            "value": "Supported",
            "usage": "Use only when the buyer is clearly audit-sensitive.",
            "source_pages": ["certificates.html", "quality.html"],
        },
        "reach_prop65": {
            "label": "REACH / Prop 65",
            "email_phrase": "REACH / Prop 65 documentation on request",
            "value": "On request",
            "usage": "Use only when the buyer explicitly cares about material compliance detail.",
            "source_pages": ["certificates.html", "quality.html"],
        },
    },
    "operational_facts": {
        "quote_dfm_turnaround": {
            "label": "Quote / DFM turnaround",
            "value": "within 48 hours",
            "usage": "Use for buyers who care about response speed or sample-development coordination.",
            "source_pages": ["about.html", "contact.html", "index.html"],
        },
        "sample_lead_time": {
            "label": "Sample lead time",
            "value": "7-14 days",
            "usage": "Safe to use in first-touch emails when sample speed matters.",
            "source_pages": ["about.html", "contact.html", "quality.html", "index.html"],
        },
        "silicone_moq_simple": {
            "label": "MOQ for simple silicone parts",
            "value": "2,000 units",
            "usage": "Use when the buyer is likely screening suppliers by MOQ.",
            "source_pages": ["contact.html", "index.html"],
        },
        "plastic_moq_standard": {
            "label": "MOQ for plastic injection parts",
            "value": "5,000 units",
            "usage": "Use for plastic-led projects, not silicone-first outreach.",
            "source_pages": ["contact.html", "index.html"],
        },
        "trial_run": {
            "label": "Trial run",
            "value": "500 units with a one-off setup fee",
            "usage": "Use only when the buyer asks about low-volume pilots or trial orders.",
            "source_pages": ["contact.html"],
        },
        "on_time_shipment_2025": {
            "label": "On-time shipment",
            "value": "99.4%",
            "usage": "Use as a credibility cue for logistics-sensitive buyers.",
            "source_pages": ["quality.html", "index.html"],
        },
        "field_defect_rate_2025": {
            "label": "Field defect rate",
            "value": "0.18%",
            "usage": "Use sparingly and only if a buyer clearly cares about QC metrics.",
            "source_pages": ["quality.html", "index.html"],
        },
    },
    "email_playbook": {
        "first_touch_eu_food_contact": ["lfgb", "fda", "iso9001"],
        "audit_sensitive": ["bsci", "smeta", "iso9001"],
        "default_signature": {
            "sender_name": "Dingsheng Sales Team",
            "company_name": "Dingsheng Plastic & Silicone Co., Ltd.",
            "sales_email": "admin@hzhesheng.com.cn",
            "phone_whatsapp": "+86 150 1809 1819",
        },
        "usage_notes": [
            "For Germany or EU kitchenware first-touch emails, lead with LFGB, then FDA, then ISO 9001.",
            "For distributor or importer buyers, prefer one operational fact such as sample lead time, MOQ, or quote turnaround over stacked adjectives.",
            "Use only one concrete fact in most first-touch emails unless an extra proof point clearly lowers buyer risk.",
            "Keep OEM/ODM wording directional unless upstream evidence explicitly supports detailed execution claims.",
            "Do not use MOQ or lead-time numbers unless they are public, relevant, and the email stays concise.",
            "Prefer one concrete proof point or one concrete numeric fact over extra generic adjectives.",
            "Use the smallest useful subset of facts that fits the buyer's likely sourcing logic.",
        ],
    },
}


def default_factory_knowledge() -> dict[str, Any]:
    return deepcopy(DEFAULT_FACTORY_KNOWLEDGE)


def get_prioritized_proof_points(
    knowledge: dict[str, Any] | None = None,
    *,
    scenario: str = "first_touch_eu_food_contact",
) -> list[dict[str, Any]]:
    source = knowledge or DEFAULT_FACTORY_KNOWLEDGE
    proof_points = source.get("proof_points", {}) or {}
    playbook = source.get("email_playbook", {}) or {}
    keys = list(playbook.get(scenario, []) or [])
    facts: list[dict[str, Any]] = []
    for key in keys:
        item = proof_points.get(key)
        if item:
            facts.append({"key": key, **item})
    return facts


def get_operational_fact(
    key: str,
    knowledge: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    source = knowledge or DEFAULT_FACTORY_KNOWLEDGE
    facts = source.get("operational_facts", {}) or {}
    item = facts.get(key)
    if not item and key == "quote_turnaround":
        item = facts.get("quote_dfm_turnaround")
    if not item:
        return None
    return {"key": key, **item}


def factory_context_summary(knowledge: dict[str, Any] | None = None) -> str:
    source = knowledge or DEFAULT_FACTORY_KNOWLEDGE
    identity = source.get("identity", {}) or {}
    products = ", ".join(FACTORY_PROFILE["core_products"])
    capabilities = "; ".join(FACTORY_PROFILE["core_capabilities"][:4])
    credibility = "; ".join(FACTORY_PROFILE["credibility_points"][:4])
    return (
        f"Company: {identity.get('company_name', FACTORY_PROFILE['company_name'])} "
        f"({identity.get('company_type', FACTORY_PROFILE['company_type'])}). "
        f"Products: {products}. "
        f"Capabilities: {capabilities}. "
        f"Credibility: {credibility}."
    )


def factory_email_fact_summary(knowledge: dict[str, Any] | None = None) -> str:
    source = knowledge or DEFAULT_FACTORY_KNOWLEDGE
    proofs = get_prioritized_proof_points(source)
    sample_lead = get_operational_fact("sample_lead_time", source)
    quote_turnaround = get_operational_fact("quote_dfm_turnaround", source)
    silicone_moq = get_operational_fact("silicone_moq_simple", source)
    signature = (source.get("email_playbook", {}) or {}).get("default_signature", {}) or {}

    proof_text = ", ".join(item.get("label", "") for item in proofs if item.get("label"))
    parts = []
    if proof_text:
        parts.append(f"Priority proof points: {proof_text}.")
    if sample_lead:
        parts.append(f"Sample lead time: {sample_lead.get('value', '')}.")
    if quote_turnaround:
        parts.append(f"Quote / DFM turnaround: {quote_turnaround.get('value', '')}.")
    if silicone_moq:
        parts.append(f"Simple silicone MOQ: {silicone_moq.get('value', '')}.")
    if signature:
        parts.append(
            "Signature default: "
            f"{signature.get('sender_name', '')}, {signature.get('company_name', '')}, "
            f"{signature.get('sales_email', '')}, {signature.get('phone_whatsapp', '')}."
        )
    return " ".join(part for part in parts if part).strip()


def select_matching_strengths(
    customer_type: str,
    website_summary: str,
    evidence_quotes: list[str],
) -> list[str]:
    text = " ".join([customer_type, website_summary, *evidence_quotes]).lower()
    strengths: list[str] = []

    if any(marker in text for marker in ("private label", "oem", "own brand", "eigenmarke")):
        strengths.append("OEM/ODM support and private-label execution")
    if any(
        marker in text
        for marker in (
            "kitchen",
            "utensil",
            "baking",
            "housewares",
            "brush",
            "spatula",
            "scraper",
            "catalogue",
        )
    ):
        strengths.append(
            "Focused supply in silicone kitchen tools, baking accessories, and daily-use kitchen items"
        )
    if any(marker in text for marker in ("distributor", "wholesaler", "importer", "supplier")):
        strengths.append(
            "Stable export supply for channel buyers, with flexible MOQ and consistent lead-time support"
        )
    if any(marker in text for marker in ("food", "bakery", "hotel", "gastro", "kitchen")):
        strengths.append(
            "Food-contact production backed by LFGB/FDA compliance support and an ISO 9001-certified quality system"
        )

    if not strengths:
        strengths.append(
            "Professional supply support for silicone and plastic kitchen products with export experience"
        )

    return strengths[:2]
