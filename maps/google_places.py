from __future__ import annotations

import json
import re
import unicodedata
from typing import Any
from urllib.parse import urlparse

import requests

from config.settings import Settings
from database.models import Lead


class GooglePlacesClient:
    MAX_TEXT_SEARCH_RESULTS_PER_PAGE = 20
    MAX_TEXT_SEARCH_RESULTS_TOTAL = 60
    RETAIL_NEGATIVE_MARKERS = (
        "store",
        "shop",
        "retail",
        "supermarket",
        "shopping_mall",
        "home_improvement_store",
        "department_store",
        "furniture_store",
    )
    PRODUCT_FIT_POSITIVE_MARKERS = (
        "silicone",
        "silicone products",
        "silicone kitchenware",
        "silicone kitchen tools",
        "silicone housewares",
        "kitchen accessories",
        "kitchen accessory",
        "kitchen tool",
        "kitchen tools",
        "kitchen utensil",
        "kitchen utensils",
        "kitchenware",
        "housewares",
        "homeware",
        "homewares",
        "household products",
        "utensils",
        "baking tools",
        "baking accessories",
        "baking supplies",
        "bakeware",
        "bakery",
        "pastry",
        "spatula",
        "spatulas",
        "scraper",
        "scrapers",
        "brush",
        "brushes",
        "kitchen gadgets",
        "tableware",
        "private label",
        "oem",
        "odm",
    )
    PRODUCT_FIT_NEGATIVE_MARKERS = (
        "grosskuchengerate",
        "grosskuchentechnik",
        "commercial kitchen",
        "gastronomiebedarf",
        "catering equipment",
        "kitchen system",
        "industrial kitchen",
        "pizza oven",
        "refrigeration",
        "ventilation",
        "dishwasher",
        "food processing machine",
        "machinery",
        "vegetable cutter",
        "wash system",
        "stainless steel kitchen",
    )
    B2B_POSITIVE_MARKERS = (
        "importer",
        "distributor",
        "wholesaler",
        "supplier",
        "manufacturer",
        "private label",
        "oem",
        "odm",
        "own brand",
        "brand owner",
        "eigenmarke",
        "dealer",
        "reseller",
        "sourcing",
        "procurement",
        "housewares",
        "homeware",
        "kitchenware",
        "b2b",
    )
    B2B_STRONG_MARKERS = (
        "private label",
        "oem",
        "odm",
        "importer",
        "distributor",
        "wholesaler",
        "brand owner",
        "eigenmarke",
        "dealer",
        "reseller",
        "b2b",
        "procurement",
        "sourcing",
    )
    RETAIL_STRONG_MARKERS = (
        "retail",
        "store",
        "shop",
        "shopping mall",
        "supermarket",
        "department store",
        "furniture store",
        "furniture_store",
        "home goods store",
        "home_goods_store",
        "home improvement store",
        "home_improvement_store",
        "gift shop",
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.last_mode = "sample"
        self.last_error = ""

    def search_leads(
        self,
        query: str,
        country: str,
        limit: int = 5,
        search_mode: str = "balanced",
    ) -> list[Lead]:
        if self.settings.google_maps_api_key:
            try:
                leads = self._search_with_api(query, country, limit, search_mode)
                self.last_mode = "api"
                self.last_error = ""
                return leads
            except requests.RequestException as exc:
                self.last_error = self._format_request_exception(exc)
            except Exception as exc:  # pragma: no cover
                self.last_error = f"{type(exc).__name__}: {exc}"
            self.last_mode = "api"
            return []

        self.last_error = "GOOGLE_MAPS_API_KEY is empty, fallback sample data used."
        self.last_mode = "sample"
        return self._sample_leads(query, country, limit)

    def status_summary(self) -> dict[str, str | bool]:
        return {
            "configured": bool(self.settings.google_maps_api_key),
            "mode": self.last_mode,
            "last_error": self.last_error,
            "uses_env_proxy": self.settings.google_maps_use_env_proxy,
            "explicit_proxy_set": bool(self.settings.google_maps_proxy_url),
        }

    def _search_with_api(
        self,
        query: str,
        country: str,
        limit: int,
        search_mode: str,
    ) -> list[Lead]:
        text_query = f"{query} {country}".strip()
        requested_limit = max(1, int(limit))
        candidate_count = self._candidate_fetch_count(requested_limit, search_mode)
        places = self._search_text_places(text_query, candidate_count)
        leads = [self._lead_from_place(place, country, query) for place in places]
        ranked = self._rank_b2b_leads(leads, query, search_mode, limit=requested_limit)
        final_leads: list[Lead] = []
        for lead in ranked[:requested_limit]:
            final_leads.append(self._enrich_lead_details(lead))
        return final_leads

    def _candidate_fetch_count(self, limit: int, search_mode: str) -> int:
        multiplier = 4 if search_mode == "broad" else 3 if search_mode == "balanced" else 2
        floor = 20 if search_mode in {"balanced", "broad"} else 10
        return min(
            max(limit * multiplier, limit, floor),
            self.MAX_TEXT_SEARCH_RESULTS_TOTAL,
        )

    def _search_text_places(self, text_query: str, candidate_count: int) -> list[dict[str, Any]]:
        session = self._session()
        places: list[dict[str, Any]] = []
        seen_place_ids: set[str] = set()
        seen_tokens: set[str] = set()
        next_page_token = ""

        while len(places) < candidate_count:
            page_size = min(
                candidate_count - len(places),
                self.MAX_TEXT_SEARCH_RESULTS_PER_PAGE,
            )
            payload: dict[str, Any] = {
                "textQuery": text_query,
                "pageSize": page_size,
            }
            if next_page_token:
                payload["pageToken"] = next_page_token

            response = session.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": self.settings.google_maps_api_key,
                    "X-Goog-FieldMask": (
                        "places.id,places.displayName,places.formattedAddress,"
                        "places.primaryType"
                    ),
                },
                json=payload,
                timeout=self.settings.request_timeout_seconds,
            )
            response.raise_for_status()
            page_payload = response.json()
            page_places = page_payload.get("places", [])
            for place in page_places:
                place_id = str(place.get("id", "")).strip()
                dedupe_key = place_id or self._normalize_text(
                    " ".join(
                        [
                            str(place.get("displayName", {}).get("text", "")),
                            str(place.get("formattedAddress", "")),
                        ]
                    )
                )
                if not dedupe_key or dedupe_key in seen_place_ids:
                    continue
                seen_place_ids.add(dedupe_key)
                places.append(place)
                if len(places) >= candidate_count:
                    break

            next_page_token = str(page_payload.get("nextPageToken", "")).strip()
            if not next_page_token or next_page_token in seen_tokens or not page_places:
                break
            seen_tokens.add(next_page_token)

        return places

    def _lead_from_place(self, place: dict[str, Any], country: str, query: str) -> Lead:
        display_name = place.get("displayName", {}).get("text", "Unknown Company")
        return Lead(
            place_id=str(place.get("id", "")).strip() or display_name,
            company_name=display_name,
            country=country,
            address=place.get("formattedAddress", ""),
            industry=place.get("primaryType", ""),
            search_keyword=query,
        )

    def _enrich_lead_details(self, lead: Lead) -> Lead:
        if not lead.place_id:
            return lead
        try:
            details = self._place_details(lead.place_id)
        except requests.RequestException:
            return lead

        lead.address = details.get("formattedAddress") or lead.address
        lead.website = details.get("websiteUri", "") or lead.website
        lead.phone = details.get("internationalPhoneNumber", "") or lead.phone
        lead.industry = details.get("primaryType", "") or lead.industry
        return lead

    def _place_details(self, place_id: str) -> dict[str, Any]:
        response = self._session().get(
            f"https://places.googleapis.com/v1/places/{place_id}",
            headers={
                "X-Goog-Api-Key": self.settings.google_maps_api_key,
                "X-Goog-FieldMask": (
                    "displayName,formattedAddress,internationalPhoneNumber,"
                    "websiteUri,primaryType"
                ),
            },
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def _session(self) -> requests.Session:
        session = requests.Session()
        session.trust_env = self.settings.google_maps_use_env_proxy
        if self.settings.google_maps_proxy_url:
            session.proxies.update(
                {
                    "http": self.settings.google_maps_proxy_url,
                    "https": self.settings.google_maps_proxy_url,
                }
            )
        return session

    def _format_request_exception(self, exc: requests.RequestException) -> str:
        response = getattr(exc, "response", None)
        if response is None:
            return f"{type(exc).__name__}: {exc}"

        body = response.text.strip()
        parsed_body = body
        if body:
            try:
                parsed_body = json.dumps(response.json(), ensure_ascii=False)
            except ValueError:
                parsed_body = body
        return (
            f"{type(exc).__name__}: status={response.status_code}, "
            f"body={parsed_body[:1200]}"
        )

    def _sample_leads(self, query: str, country: str, limit: int) -> list[Lead]:
        keyword = query.lower().strip() or "supplier"
        base_names = [
            "Northbridge",
            "Aster",
            "Summit",
            "Harbor",
            "Brightline",
            "Atlas",
        ]
        industry = self._guess_industry(keyword)
        leads: list[Lead] = []
        for index, prefix in enumerate(base_names[:limit], start=1):
            company_name = f"{prefix} {industry.title()} {country}"
            slug = self._slugify(company_name)
            leads.append(
                Lead(
                    place_id=f"sample-{slug}",
                    company_name=company_name,
                    country=country,
                    city="Sample City",
                    address=f"{index} Market Street, {country}",
                    website=f"https://{slug}.example",
                    phone=f"+00-000-{index:04d}",
                    industry=industry,
                    search_keyword=query,
                )
            )
        return leads

    def _rank_b2b_leads(
        self,
        leads: list[Lead],
        query: str,
        search_mode: str,
        limit: int | None = None,
    ) -> list[Lead]:
        ranked = sorted(leads, key=lambda lead: self._lead_score(lead, query), reverse=True)
        if not ranked:
            return []
        qualified = [lead for lead in ranked if self._lead_qualifies(lead, query, search_mode)]
        permissive = [lead for lead in ranked if self._lead_is_permissive_candidate(lead, query)]
        non_excluded = [lead for lead in ranked if self._lead_is_non_excluded(lead)]
        if search_mode == "broad":
            primary = non_excluded or permissive or qualified or ranked
            return self._fill_ranked_results(primary, [], ranked, limit)
        if search_mode == "strict":
            primary = qualified
            secondary = permissive if not qualified else []
            return self._fill_ranked_results(primary, secondary, ranked, limit)
        if not qualified:
            return self._fill_ranked_results(permissive or non_excluded, [], ranked, limit)
        if self._query_has_b2b_intent(query):
            return self._fill_ranked_results(qualified, permissive, ranked, limit)
        if len(qualified) >= min(3, len(ranked)):
            return self._fill_ranked_results(qualified, [], ranked, limit)
        return self._fill_ranked_results(ranked, [], ranked, limit)

    def _fill_ranked_results(
        self,
        primary: list[Lead],
        secondary: list[Lead],
        ranked: list[Lead],
        limit: int | None,
    ) -> list[Lead]:
        merged: list[Lead] = []
        seen: set[str] = set()
        for bucket in (primary, secondary, ranked):
            for lead in bucket:
                dedupe_key = lead.place_id or self._normalize_text(lead.company_name)
                if not dedupe_key or dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                merged.append(lead)
                if limit is not None and len(merged) >= limit:
                    return merged
        return merged

    def _lead_score(self, lead: Lead, query: str) -> tuple[int, int, int]:
        lead_haystack = self._normalize_text(
            " ".join([lead.company_name, lead.industry, lead.website, lead.address])
        )
        haystack = self._normalize_text(
            " ".join([lead.company_name, lead.industry, lead.website, lead.address])
        )
        query_stack = self._normalize_text(query)
        positive = sum(
            1 for marker in self.B2B_POSITIVE_MARKERS if self._contains_marker(lead_haystack, marker)
        )
        strong_b2b = sum(
            1 for marker in self.B2B_STRONG_MARKERS if self._contains_marker(lead_haystack, marker)
        )
        negative = sum(
            1 for marker in self.RETAIL_NEGATIVE_MARKERS if self._contains_marker(lead_haystack, marker)
        )
        retail_strong = sum(
            1 for marker in self.RETAIL_STRONG_MARKERS if self._contains_marker(lead_haystack, marker)
        )
        product_fit_positive = sum(
            1 for marker in self.PRODUCT_FIT_POSITIVE_MARKERS if self._contains_marker(lead_haystack, marker)
        )
        product_fit_negative = sum(
            1 for marker in self.PRODUCT_FIT_NEGATIVE_MARKERS if self._contains_marker(lead_haystack, marker)
        )
        query_wants_silicone = any(
            self._contains_marker(query_stack, marker)
            for marker in (
                "silicone",
                "silicone products",
                "silicone kitchenware",
                "spatula",
                "scraper",
                "brush",
                "baking",
                "bakeware",
                "housewares",
                "homeware",
                "kitchenware",
                "kitchen accessory",
            )
        )
        query_wants_b2b = any(
            self._contains_marker(query_stack, marker)
            for marker in ("importer", "distributor", "wholesaler", "private label", "oem", "brand")
        )

        fit_score = (
            product_fit_positive * 3
            + positive * 2
            + strong_b2b * 2
            - negative * 2
            - retail_strong * 2
            - product_fit_negative * 3
        )
        if self._is_hard_excluded(lead_haystack):
            fit_score -= 10
        if self._country_matches_query(lead, query):
            fit_score += 2
        if query_wants_silicone:
            fit_score += product_fit_positive * 2
            fit_score -= product_fit_negative * 2
        if query_wants_b2b:
            fit_score += strong_b2b * 2
            fit_score -= retail_strong * 2

        has_website = 1 if lead.website else 0
        has_phone = 1 if lead.phone else 0
        return (
            fit_score,
            strong_b2b + product_fit_positive - product_fit_negative,
            has_website + has_phone,
        )

    def _lead_qualifies(self, lead: Lead, query: str, search_mode: str = "balanced") -> bool:
        haystack = self._normalize_text(
            " ".join([lead.company_name, lead.industry, lead.website, lead.address])
        )
        product_fit_positive = sum(
            1 for marker in self.PRODUCT_FIT_POSITIVE_MARKERS if self._contains_marker(haystack, marker)
        )
        product_fit_negative = sum(
            1 for marker in self.PRODUCT_FIT_NEGATIVE_MARKERS if self._contains_marker(haystack, marker)
        )
        strong_b2b = sum(
            1 for marker in self.B2B_STRONG_MARKERS if self._contains_marker(haystack, marker)
        )
        retail_strong = sum(
            1 for marker in self.RETAIL_STRONG_MARKERS if self._contains_marker(haystack, marker)
        )
        if self._is_hard_excluded(haystack):
            return False
        query_stack = self._normalize_text(query)
        query_wants_b2b = self._query_has_b2b_intent(query)
        query_wants_silicone = any(
            self._contains_marker(query_stack, marker)
            for marker in (
                "silicone",
                "silicone products",
                "silicone kitchenware",
                "spatula",
                "scraper",
                "brush",
                "baking",
                "bakeware",
                "housewares",
                "homeware",
                "kitchenware",
            )
        )

        if search_mode == "strict":
            qualifies = (
                (product_fit_positive >= 1 and strong_b2b >= 1)
                or (product_fit_positive >= 2 and product_fit_negative == 0)
                or (strong_b2b >= 2 and retail_strong == 0 and product_fit_negative == 0)
            )
            if query_wants_b2b:
                qualifies = qualifies and strong_b2b >= 1
            if query_wants_silicone:
                qualifies = qualifies and product_fit_positive >= 1 and product_fit_negative == 0
            return qualifies

        if search_mode == "broad":
            qualifies = (
                strong_b2b >= 1
                or product_fit_positive >= 1
                or (retail_strong == 0 and product_fit_negative == 0)
            )
            if query_wants_silicone:
                qualifies = qualifies and product_fit_negative == 0
            return qualifies

        qualifies = (
            (product_fit_positive >= 1 and (strong_b2b >= 1 or retail_strong == 0))
            or (strong_b2b >= 1 and retail_strong == 0 and product_fit_negative == 0)
            or (product_fit_positive >= 2 and product_fit_negative == 0)
        )
        if query_wants_b2b:
            qualifies = qualifies and (strong_b2b >= 1 or product_fit_positive >= 1)
        if query_wants_silicone:
            qualifies = qualifies and product_fit_negative == 0 and (
                product_fit_positive >= 1 or strong_b2b >= 1
            )
        return qualifies

    def _is_hard_excluded(self, haystack: str) -> bool:
        return (
            any(self._contains_marker(haystack, marker) for marker in self.RETAIL_STRONG_MARKERS)
            or any(self._contains_marker(haystack, marker) for marker in self.PRODUCT_FIT_NEGATIVE_MARKERS)
        )

    def _lead_is_permissive_candidate(self, lead: Lead, query: str) -> bool:
        haystack = self._normalize_text(
            " ".join([lead.company_name, lead.industry, lead.website, lead.address])
        )
        if self._is_hard_excluded(haystack):
            return False
        positive = sum(
            1 for marker in self.B2B_POSITIVE_MARKERS if self._contains_marker(haystack, marker)
        )
        product_fit_positive = sum(
            1 for marker in self.PRODUCT_FIT_POSITIVE_MARKERS if self._contains_marker(haystack, marker)
        )
        query_stack = self._normalize_text(query)
        query_wants_silicone = any(
            self._contains_marker(query_stack, marker)
            for marker in (
                "silicone",
                "silicone products",
                "silicone kitchenware",
                "spatula",
                "scraper",
                "brush",
                "baking",
                "bakeware",
                "housewares",
                "homeware",
                "kitchenware",
            )
        )
        if query_wants_silicone:
            return product_fit_positive >= 1
        return positive >= 1 or product_fit_positive >= 1

    def _lead_is_non_excluded(self, lead: Lead) -> bool:
        haystack = self._normalize_text(
            " ".join([lead.company_name, lead.industry, lead.website, lead.address])
        )
        return not self._is_hard_excluded(haystack)

    def _query_has_b2b_intent(self, query: str) -> bool:
        query_stack = self._normalize_text(query)
        return any(
            self._contains_marker(query_stack, marker)
            for marker in (
                "importer",
                "distributor",
                "wholesaler",
                "supplier",
                "manufacturer",
                "private label",
                "oem",
                "odm",
                "brand",
                "sourcing",
                "procurement",
            )
        )

    def _country_matches_query(self, lead: Lead, query: str) -> bool:
        query_stack = self._normalize_text(query)
        if " germany" in f" {query_stack} ":
            return " germany " in f" {self._normalize_text(lead.address)} "
        return True

    def _normalize_text(self, value: str) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = text.encode("ascii", "ignore").decode("ascii")
        text = text.lower()
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _contains_marker(self, haystack: str, marker: str) -> bool:
        normalized_marker = self._normalize_text(marker)
        if not normalized_marker:
            return False
        return f" {normalized_marker} " in f" {haystack} "

    def _guess_industry(self, keyword: str) -> str:
        if "light" in keyword or "led" in keyword:
            return "lighting distributor"
        if "furniture" in keyword:
            return "furniture wholesaler"
        if "solar" in keyword:
            return "solar supplier"
        if "hardware" in keyword:
            return "hardware importer"
        if any(
            token in keyword
            for token in (
                "silicone",
                "spatula",
                "scraper",
                "brush",
                "baking",
                "bakeware",
                "kitchenware",
                "housewares",
                "homeware",
            )
        ):
            return "kitchen tools distributor"
        return "b2b supplier"

    def _slugify(self, value: str) -> str:
        return "-".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())

    def domain_from_url(self, website: str) -> str:
        return urlparse(website).netloc
