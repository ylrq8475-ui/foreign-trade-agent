from __future__ import annotations


FACTORY_PROFILE = {
    "company_name": "Plastic-Dingsheng",
    "company_type": "food-grade silicone kitchenware manufacturer and professional supplier",
    "core_products": [
        "silicone spatulas",
        "silicone scrapers",
        "silicone brushes",
        "baking tools",
        "daily kitchen accessories",
        "collapsible silicone products",
        "selected plastic kitchenware",
    ],
    "core_capabilities": [
        "OEM and ODM development",
        "Pantone color matching",
        "logo printing and laser logo options",
        "food-grade silicone and plastic production",
        "customer-designated material brands accepted",
        "in-house material mixing, adjusting, and cutting",
        "one-piece silicone product design support",
        "silicone overmold with nylon or metal component support",
    ],
    "credibility_points": [
        "20+ years manufacturing experience",
        "6500 m2 factory with 150+ staff",
        "15 engineers and 20 QC specialists",
        "FDA and LFGB compliant materials",
        "TUV and SGS food-contact testing support",
        "export experience across Europe, the USA, Australia, and Japan",
        "10+ plate vulcanizing machines for silicone production",
        "10+ injection machines for plastic production",
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


def select_matching_strengths(
    customer_type: str,
    website_summary: str,
    evidence_quotes: list[str],
) -> list[str]:
    text = " ".join([customer_type, website_summary, *evidence_quotes]).lower()
    strengths: list[str] = []

    if any(marker in text for marker in ("private label", "oem", "own brand", "eigenmarke")):
        strengths.append(
            "OEM/ODM support with Pantone color matching, logo printing, and private-label execution"
        )
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
            "Food-contact production with FDA/LFGB-compliant materials and TUV/SGS testing support"
        )

    if not strengths:
        strengths.append(
            "Professional supply support for silicone and plastic kitchen products with OEM/ODM and export experience"
        )

    return strengths[:2]


def factory_context_summary() -> str:
    products = ", ".join(FACTORY_PROFILE["core_products"])
    capabilities = "; ".join(FACTORY_PROFILE["core_capabilities"][:4])
    credibility = "; ".join(FACTORY_PROFILE["credibility_points"][:4])
    return (
        f"Company: {FACTORY_PROFILE['company_name']} ({FACTORY_PROFILE['company_type']}). "
        f"Products: {products}. "
        f"Capabilities: {capabilities}. "
        f"Credibility: {credibility}."
    )
