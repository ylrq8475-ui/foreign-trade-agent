from __future__ import annotations

import re

from database.models import ParsedWebsite, WebsiteSnapshot


class WebsiteParser:
    NOISE_MARKERS = (
        "cookie",
        "datenschutz",
        "privacy policy",
        "accept all",
        "allow all",
        "granted",
        "denied",
        "javascript",
        "newsletter",
        "google tag manager",
        "consent",
        "tracking",
        "versandkosten",
        "warenkorb",
        "mein konto",
        "anmelden",
        "auf lager",
        "checkout",
        "add to cart",
        "website: amazon",
        "website: ebay",
        "website: otto",
        "website: kaufland",
        "website: qvc",
        "catalogue contact jobs",
        "impressum",
        "agb",
        "hinweise zur entsorgung",
        "kontaktiere uns",
        "falls du eine frage",
        "products & service magazine",
        "contact jobs men",
        "where service begins we are",
        "spot on new items",
        "jetzt entdecken",
        "weiterlesen",
        "jetzt ansehen",
        "sortierung",
        "filter schließen",
    )

    NAVIGATION_TERMS = {
        "home",
        "about",
        "products",
        "service",
        "services",
        "catalogue",
        "catalog",
        "contact",
        "jobs",
        "menu",
        "shop",
        "magazine",
        "news",
        "login",
        "account",
        "cart",
    }

    PRODUCT_KEYWORDS = [
        "silicone spatula",
        "silicone scraper",
        "silicone brush",
        "kitchen accessories",
        "kitchen tools",
        "kitchenware",
        "housewares",
        "utensils",
        "baking tools",
        "baking supplies",
        "bakeware",
        "private label",
        "food grade",
    ]

    PAGE_TYPE_BONUS = {
        "private_label": 14,
        "products": 6,
        "brand": 4,
        "about": 8,
        "service": 7,
        "home": 1,
        "contact": 1,
        "page": 0,
    }

    CATEGORY_PRIORITY = {
        "company_positioning": 5,
        "product_range": 4,
        "private_label": 3,
        "brand_owner": 2,
        "brand_story": 1,
        "general": 0,
    }

    def parse(
        self, snapshot: WebsiteSnapshot, fallback_industry: str = ""
    ) -> ParsedWebsite:
        text = snapshot.combined_text.strip()
        if not text:
            return ParsedWebsite(
                website_summary="No readable website content available.",
                main_products=[],
                customer_type=fallback_industry or "unknown",
                personalization_points=[],
                source_url=snapshot.website,
                source_snippet="",
                confidence_score=0.2,
                language="unknown",
                extraction_status="failed",
                review_required=True,
                evidence=[],
            )

        candidates = self._collect_candidates(snapshot)
        ranked_candidates = sorted(candidates, key=lambda item: int(item["score"]), reverse=True)
        ranked_blocks = [str(item["text"]) for item in ranked_candidates if item["kind"] == "block"]
        quality_ok = self._content_quality_ok(text, ranked_candidates)
        summary = self._build_summary(ranked_candidates)
        main_products = self._detect_products(text, ranked_blocks)
        customer_type = self._detect_customer_type(text, fallback_industry)
        evidence = self._build_evidence(ranked_candidates, quality_ok)
        personalization_points = self._build_personalization_points(text, main_products, ranked_candidates)
        confidence = self._confidence_score(evidence, quality_ok, ranked_blocks)
        extraction_status = "success" if quality_ok else "low_quality"
        review_required = confidence < 0.65 or not quality_ok

        if not quality_ok:
            evidence = []
            personalization_points = []

        return ParsedWebsite(
            website_summary=(
                summary
                if quality_ok and summary
                else "Website content was captured, but the extracted text quality is too low for reliable personalization."
            ),
            main_products=main_products,
            customer_type=customer_type,
            personalization_points=personalization_points,
            source_url=evidence[0]["page"] if evidence else snapshot.website,
            source_snippet=evidence[0]["quote"] if evidence else "",
            confidence_score=confidence,
            language="en",
            extraction_status=extraction_status,
            review_required=review_required,
            evidence=evidence,
        )

    def _collect_candidates(self, snapshot: WebsiteSnapshot) -> list[dict[str, object]]:
        candidates: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        for page in snapshot.pages[:6]:
            for block in page.blocks[:10]:
                key = (page.url, block.strip().lower())
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(self._candidate_record(page.url, page.page_type, block, "block"))
            for sentence in self._usable_sentences(page.text):
                key = (page.url, sentence.strip().lower())
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(self._candidate_record(page.url, page.page_type, sentence, "sentence"))
        return [item for item in candidates if int(item["score"]) > 0]

    def _candidate_record(
        self, page_url: str, page_type: str, text: str, kind: str
    ) -> dict[str, object]:
        category = self._candidate_category(text)
        score = self._candidate_score(text, page_type, kind, category)
        return {
            "page": page_url,
            "page_type": page_type,
            "text": text[:280],
            "kind": kind,
            "category": category,
            "score": score,
        }

    def _build_summary(self, ranked_candidates: list[dict[str, object]]) -> str:
        chosen: list[str] = []
        seen_fragments: set[str] = set()
        for item in self._preferred_candidates(ranked_candidates):
            text = str(item["text"])
            fragments = [
                fragment.strip()
                for fragment in re.split(r"(?<=[\.\!\?])\s+", text)
                if fragment.strip()
            ]
            for fragment in fragments:
                normalized = fragment.lower().rstrip(".")
                if normalized in seen_fragments:
                    continue
                seen_fragments.add(normalized)
                chosen.append(fragment.rstrip("."))
                if len(chosen) >= 2:
                    break
            if len(chosen) >= 2:
                break
        return ". ".join(chosen)[:360]

    def _detect_products(self, text: str, ranked_blocks: list[str]) -> list[str]:
        searchable = " ".join(ranked_blocks[:8]) + "\n" + text
        found = [
            keyword
            for keyword in self.PRODUCT_KEYWORDS
            if keyword.lower() in searchable.lower()
        ]
        return found[:4]

    def _detect_customer_type(self, text: str, fallback_industry: str) -> str:
        normalized = text.lower()
        if "distributor" in normalized:
            return "distributor"
        if "wholesaler" in normalized:
            return "wholesaler"
        if "importer" in normalized:
            return "importer"
        if "manufacturer" in normalized:
            return "manufacturer"
        if "brand" in normalized or "private label" in normalized or "eigenmarke" in normalized:
            return "brand owner"
        if "retail" in normalized:
            return "retailer"
        return fallback_industry or "b2b buyer"

    def _build_personalization_points(
        self,
        text: str,
        products: list[str],
        ranked_candidates: list[dict[str, object]],
    ) -> list[str]:
        points: list[str] = []
        lowered = text.lower()
        top_text = " ".join(str(item["text"]).lower() for item in self._preferred_candidates(ranked_candidates)[:6])
        if "project" in lowered or "vertrieb" in lowered or "distribution" in lowered:
            points.append("Mentions commercial sales support or route-to-market capability")
        if "private label" in top_text or "oem" in top_text:
            points.append("Highlights OEM or private label cooperation")
        if "pantone" in top_text or "logo" in top_text:
            points.append("Shows signs of customization or branded product work")
        if any(marker in lowered for marker in ("distributor", "wholesaler", "importer", "supplier", "retail", "retailer", "vertrieb", "handel")) and any(
            marker in top_text for marker in ("assortment", "range", "sortiment", "collection", "kitchen", "housewares", "baking", "utensils")
        ):
            points.append("Assortment and channel focus suggest repeat-order kitchenware demand")
        if products:
            points.append(f"Website references {products[0]}")
        if any(marker in lowered for marker in ("distributor", "wholesaler", "importer", "supplier")):
            points.append("Appears to work with channel buyers rather than end consumers")
        return points[:3]

    def _build_evidence(
        self,
        ranked_candidates: list[dict[str, object]],
        quality_ok: bool,
    ) -> list[dict[str, str]]:
        if not quality_ok:
            return []
        evidence: list[dict[str, str]] = []
        seen_quotes: set[str] = set()
        for item in self._preferred_candidates(ranked_candidates):
            quote = str(item["text"])[:220]
            if quote in seen_quotes:
                continue
            seen_quotes.add(quote)
            evidence.append(
                {
                    "page": str(item["page"]),
                    "quote": quote,
                    "type": "fact",
                    "category": str(item.get("category", "general")),
                }
            )
            if len(evidence) >= 3:
                break
        return evidence

    def _usable_sentences(self, text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
        raw_chunks = re.split(r"(?<=[\.\!\?])\s+", normalized)
        sentences: list[str] = []
        for chunk in raw_chunks:
            candidate = chunk.strip().strip('"')
            candidate = re.sub(r"^https?://\S+\s*", "", candidate)
            candidate = candidate.replace("✓", " ").replace("鉁?", " ").strip()
            lowered = candidate.lower()
            if not candidate:
                continue
            if "<" in candidate or ">" in candidate:
                continue
            if any(token in candidate for token in ("/*", "*/", "{", "}", ";", "width:", "border:")):
                continue
            if any(marker in lowered for marker in ("<!doctype", "itemscope", "schema.org/webpage")):
                continue
            if any(marker in lowered for marker in self.NOISE_MARKERS):
                continue
            if len(candidate) < 35:
                continue
            if sum(ch.isalpha() for ch in candidate) < 20:
                continue
            if self._looks_like_catalog_listing(candidate):
                continue
            if self._looks_like_navigation_mix(candidate):
                continue
            if not self._looks_like_business_text(candidate):
                continue
            sentences.append(candidate)
        return sentences

    def _content_quality_ok(self, text: str, ranked_candidates: list[dict[str, object]]) -> bool:
        if not ranked_candidates:
            return False
        sample = text[:400].lower()
        if any(marker in sample for marker in ("<!doctype", "<html", "<head", "<meta")):
            return False
        if any(marker in sample for marker in ("/*", "*/", "width:", "border:", ".table", "{", "}")):
            return False
        top_candidates = self._preferred_candidates(ranked_candidates)[:3]
        block_count = sum(1 for item in top_candidates if item["kind"] == "block")
        return block_count >= 1 or len(top_candidates) >= 2

    def _confidence_score(
        self,
        evidence: list[dict[str, str]],
        quality_ok: bool,
        ranked_blocks: list[str],
    ) -> float:
        if not quality_ok:
            return 0.2
        if evidence and len(ranked_blocks) >= 2:
            return 0.82
        if evidence:
            return 0.7
        return 0.45

    def _looks_like_business_text(self, sentence: str) -> bool:
        lowered = sentence.lower()
        positive_markers = (
            "kitchen",
            "housewares",
            "baking",
            "bakery",
            "utensils",
            "spatula",
            "scraper",
            "brush",
            "gadget",
            "cookware",
            "tableware",
            "private label",
            "oem",
            "pantone",
            "logo",
            "manufacturer",
            "supplier",
            "distributor",
            "importer",
            "wholesale",
            "product",
            "products",
            "solutions",
            "company",
            "service",
            "project",
            "hotel",
            "gastro",
            "kunden",
            "produkte",
            "handel",
            "technik",
            "vertrieb",
            "eigenmarke",
            "innovation",
        )
        return any(marker in lowered for marker in positive_markers)

    def _candidate_score(self, text: str, page_type: str, kind: str, category: str) -> int:
        lowered = text.lower()
        positive = sum(
            1
            for marker in (
                "kitchen",
                "housewares",
                "baking",
                "bakery",
                "utensils",
                "spatula",
                "scraper",
                "brush",
                "gadget",
                "cookware",
                "tableware",
                "private label",
                "oem",
                "pantone",
                "logo",
                "supplier",
                "distributor",
                "importer",
                "wholesaler",
                "manufacturer",
                "produkte",
                "vertrieb",
                "eigenmarke",
                "innovation",
                "trusted",
                "hotel",
                "gastro",
                "food grade",
                "fda",
                "lfgb",
            )
            if marker in lowered
        )
        positive += sum(
            2
            for marker in (
                "private label",
                "supplier",
                "distributor",
                "importer",
                "wholesaler",
                "food grade",
                "fda",
                "lfgb",
            )
            if marker in lowered
        )
        negative = sum(
            1
            for marker in (
                "commercial kitchen",
                "catering equipment",
                "pizza oven",
                "versandkosten",
                "warenkorb",
                "sale",
                "neuheiten",
                "auf lager",
                "katalogseite",
                "artikelnummer",
                "spam",
                "formulare",
                "abbrechen",
                "cookie",
                "consent",
                "newsletter",
                "captcha",
                "bots",
                "tracking",
                "widerruf",
                "datenschutz",
                *self.NOISE_MARKERS,
            )
            if marker in lowered
        )
        if re.search(r"\b\d{3,4}\b", text):
            negative += 1
        if self._looks_like_catalog_listing(text):
            negative += 4
        if self._looks_like_navigation_mix(text):
            negative += 4
        positive += self.CATEGORY_PRIORITY.get(category, 0)
        if category == "brand_story":
            negative += 1
        if kind == "block":
            positive += 2
        positive += self.PAGE_TYPE_BONUS.get(page_type, 0)
        return positive - negative

    def _looks_like_navigation_mix(self, text: str) -> bool:
        lowered = text.lower()
        tokens = re.findall(r"[A-Za-zÄÖÜäöü]+", lowered)
        if len(tokens) < 5:
            return False
        nav_count = sum(1 for token in tokens if token in self.NAVIGATION_TERMS)
        short_count = sum(1 for token in tokens if len(token) <= 5)
        if nav_count >= 3:
            return True
        if nav_count >= 2 and short_count >= max(4, len(tokens) // 2):
            return True
        if "where service begins" in lowered and nav_count >= 2:
            return True
        return False

    def _looks_like_catalog_listing(self, text: str) -> bool:
        lowered = text.lower()
        if lowered.count(" details ") >= 2:
            return True
        if lowered.count(" jetzt ansehen ") >= 2:
            return True
        if lowered.count(" weiterlesen ") >= 2:
            return True
        if sum(1 for token in ("details", "jetzt ansehen", "weiterlesen") if token in lowered) >= 2:
            return True
        return False

    def _candidate_category(self, text: str) -> str:
        lowered = text.lower()
        if any(
            marker in lowered
            for marker in (
                "supplier",
                "distributor",
                "wholesaler",
                "importer",
                "vertriebsexperten",
                "führenden supplier",
                "leading supplier",
                "specialist",
                "serving",
            )
        ):
            return "company_positioning"
        if "private label" in lowered:
            return "private_label"
        if any(marker in lowered for marker in ("eigenmarke", "own brand")):
            return "brand_owner"
        if any(
            marker in lowered
            for marker in (
                "sortiment",
                "assortment",
                "products",
                "article",
                "artikel",
                "kitchen tools",
                "housewares",
                "baking",
                "utensils",
                "mehr als",
            )
        ):
            return "product_range"
        if any(
            marker in lowered
            for marker in (
                "collection",
                "lifestyle",
                "unikat",
                "new items",
                "spot on",
                "schönsten form",
            )
        ):
            return "brand_story"
        return "general"

    def _preferred_candidates(
        self, ranked_candidates: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        return sorted(
            ranked_candidates,
            key=lambda item: (
                self.CATEGORY_PRIORITY.get(str(item.get("category", "general")), 0),
                int(item.get("score", 0)),
            ),
            reverse=True,
        )
