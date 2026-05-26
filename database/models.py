from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Lead:
    place_id: str
    company_name: str
    country: str
    city: str = ""
    address: str = ""
    website: str = ""
    phone: str = ""
    industry: str = ""
    search_keyword: str = ""
    source_platform: str = "google_places"


@dataclass
class WebsitePage:
    url: str
    title: str
    text: str
    page_type: str = "page"
    blocks: list[str] = field(default_factory=list)


@dataclass
class WebsiteSnapshot:
    website: str
    success: bool
    combined_text: str
    pages: list[WebsitePage] = field(default_factory=list)
    email_candidates: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class ParsedWebsite:
    website_summary: str
    main_products: list[str]
    customer_type: str
    personalization_points: list[str]
    source_url: str
    source_snippet: str
    confidence_score: float
    language: str
    extraction_status: str
    review_required: bool
    evidence: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CustomerProfileResult:
    customer_type: str
    main_products: list[str]
    website_summary: str
    potential_needs: list[str]
    priority: str
    confidence_score: float
    review_required: bool
    evidence: list[dict[str, Any]]
    contains_inference: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EmailDraftResult:
    subject: str
    body: str
    personalization_basis: list[dict[str, Any]]
    contains_inference: bool
    ai_tone_risk: str
    review_required: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def coerce_customer_profile(payload: dict[str, Any] | None) -> CustomerProfileResult:
    source = dict(payload or {})
    return CustomerProfileResult(
        customer_type=str(source.get("customer_type", "") or ""),
        main_products=list(source.get("main_products", []) or []),
        website_summary=str(source.get("website_summary", "") or ""),
        potential_needs=list(source.get("potential_needs", []) or []),
        priority=str(source.get("priority", "medium") or "medium"),
        confidence_score=float(source.get("confidence_score", 0.0) or 0.0),
        review_required=bool(source.get("review_required", True)),
        evidence=list(source.get("evidence", []) or []),
        contains_inference=bool(source.get("contains_inference", False)),
    )
