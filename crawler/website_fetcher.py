from __future__ import annotations

import html
import re
from urllib.parse import urljoin, urlparse

import requests

try:
    from bs4 import BeautifulSoup, Tag
except ImportError:  # pragma: no cover
    BeautifulSoup = None
    Tag = None

from config.settings import Settings
from crawler.email_extractor import extract_emails
from database.models import WebsitePage, WebsiteSnapshot

try:
    import trafilatura
except ImportError:  # pragma: no cover
    trafilatura = None


class WebsiteFetcher:
    NOISE_MARKERS = (
        "cookie",
        "privacy",
        "datenschutz",
        "newsletter",
        "versandkosten",
        "warenkorb",
        "accept all",
        "allow all",
        "consent",
        "website: amazon",
        "website: ebay",
        "website: otto",
        "website: kaufland",
        "website: qvc",
        "impressum",
        "agb",
        "hinweise zur entsorgung",
        "kontaktiere uns",
        "products & service magazine",
        "contact jobs men",
        "where service begins we are",
        "spot on new items",
        "jetzt entdecken",
        "weiterlesen",
        "jetzt ansehen",
        "sortierung",
        "filter schließen",
        " details ",
    )

    PAGE_TYPE_RULES = {
        "private_label": ("private label", "own brand", "eigenmarke", "oem", "odm"),
        "products": (
            "product",
            "products",
            "collection",
            "collections",
            "range",
            "catalog",
            "kitchen",
            "baking",
            "utensils",
            "housewares",
            "sortiment",
            "produkte",
        ),
        "about": ("about", "about us", "company", "unternehmen", "profil", "who we are"),
        "brand": ("brand", "brands", "eigenmarke", "private label"),
        "service": ("service", "solutions", "support", "vertrieb", "distribution"),
        "contact": ("contact", "kontakt", "imprint", "impressum"),
    }

    PAGE_TYPE_PRIORITY = {
        "private_label": 10,
        "products": 9,
        "brand": 8,
        "about": 7,
        "service": 6,
        "home": 5,
        "contact": 3,
        "page": 2,
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        }

    def fetch(self, website: str, company_name: str = "", industry: str = "") -> WebsiteSnapshot:
        if not website:
            return WebsiteSnapshot(
                website="",
                success=False,
                combined_text="",
                error="No website available",
            )

        if website.endswith(".example"):
            return self._build_synthetic_snapshot(website, company_name, industry)

        try:
            homepage_response = self._request(website)
            homepage = self._build_page(
                homepage_response.url,
                homepage_response.text,
                forced_page_type="home",
            )
            pages = [homepage]
            candidate_links = self._extract_candidate_links(homepage_response.url, homepage_response.text)[:6]
            for link, page_type in candidate_links:
                try:
                    response = self._request(link)
                    pages.append(
                        self._build_page(
                            response.url,
                            response.text,
                            forced_page_type=page_type,
                        )
                    )
                except requests.RequestException:
                    continue

            combined_text = "\n\n".join(
                page.text for page in pages if page.text
            ).strip()
            emails = extract_emails(combined_text)
            return WebsiteSnapshot(
                website=website,
                success=bool(combined_text),
                combined_text=combined_text,
                pages=pages,
                email_candidates=emails,
                error="" if combined_text else "No readable text extracted",
            )
        except requests.RequestException as exc:
            return WebsiteSnapshot(
                website=website,
                success=False,
                combined_text="",
                error=str(exc),
            )

    def _request(self, url: str) -> requests.Response:
        response = requests.get(
            url,
            headers=self.headers,
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        return response

    def _build_page(self, url: str, html_text: str, forced_page_type: str = "page") -> WebsitePage:
        title = self._extract_title(html_text) or url
        text, blocks = self._extract_text_and_blocks(html_text, url, title=title)
        return WebsitePage(
            url=url,
            title=title,
            text=text,
            page_type=forced_page_type,
            blocks=blocks,
        )

    def _extract_text_and_blocks(
        self, html_text: str, url: str, title: str = ""
    ) -> tuple[str, list[str]]:
        if BeautifulSoup:
            soup = BeautifulSoup(html_text, "html.parser")
            for tag in soup(["script", "style", "noscript", "template", "svg", "path"]):
                tag.decompose()
            meta_description = self._extract_meta_description(soup)
            blocks = self._extract_priority_blocks(soup)
            block_text = "\n\n".join(blocks)
            if trafilatura:
                extracted = trafilatura.extract(
                    str(soup),
                    url=url,
                    include_links=False,
                    include_images=False,
                )
                if extracted and not self._looks_like_html_noise(extracted):
                    normalized = self._normalize_text(extracted)
                    if not blocks:
                        blocks = self._derive_blocks_from_text(extracted)
                    preferred_text = block_text or normalized
                    return (
                        self._prefix_context(
                            preferred_text,
                            title=title,
                            meta_description=meta_description,
                        ),
                        blocks,
                    )
            body = soup.body or soup
            body_text = self._normalize_text(" ".join(body.stripped_strings))
            if not blocks:
                blocks = self._derive_blocks_from_text(body_text)
            preferred_text = block_text or body_text
            return (
                self._prefix_context(
                    preferred_text,
                    title=title,
                    meta_description=meta_description,
                ),
                blocks,
            )

        stripped = self._extract_text_without_parser(html_text)
        blocks = self._derive_blocks_from_text(stripped)
        return (
            self._prefix_context(
                stripped,
                title=title,
                meta_description=self._extract_meta_description_raw(html_text),
            ),
            blocks,
        )

    def _extract_priority_blocks(self, soup: BeautifulSoup) -> list[str]:
        candidates: list[tuple[tuple[int, int], str]] = []
        seen: set[str] = set()
        for element in soup.find_all(["h1", "h2", "h3", "p", "li"]):
            text = self._normalize_text(element.get_text(" ", strip=True))
            if len(text) < 25 or len(text) > 320:
                continue
            lowered = text.lower()
            if any(marker in lowered for marker in self.NOISE_MARKERS):
                continue
            if text in seen:
                continue
            seen.add(text)
            score = self._block_score(element, text)
            if score[0] <= 0:
                continue
            candidates.append((score, text))
        ranked = sorted(candidates, key=lambda item: item[0], reverse=True)
        return [text for _, text in ranked[:12]]

    def _derive_blocks_from_text(self, text: str) -> list[str]:
        normalized = text.replace("\r", "\n")
        parts = re.split(r"\n{2,}|(?<=[\.\!\?])\s+(?=[A-ZÄÖÜ])", normalized)
        blocks: list[str] = []
        seen: set[str] = set()
        for part in parts:
            candidate = self._normalize_text(part)
            if len(candidate) < 35 or len(candidate) > 280:
                continue
            lowered = candidate.lower()
            if any(marker in lowered for marker in self.NOISE_MARKERS) or any(
                marker in lowered for marker in ("tracking", "login", "checkout")
            ):
                continue
            if candidate.lower() in seen:
                continue
            seen.add(candidate.lower())
            blocks.append(candidate)
            if len(blocks) >= 12:
                break
        return blocks

    def _block_score(self, element: Tag, text: str) -> tuple[int, int]:
        lowered = text.lower()
        score = 0
        if element.name in {"h1", "h2"}:
            score += 4
        elif element.name == "h3":
            score += 2
        if element.name == "p":
            score += 1
        if element.name == "li":
            score += 1

        positive_markers = (
            "private label",
            "eigenmarke",
            "oem",
            "odm",
            "kitchen",
            "housewares",
            "utensils",
            "baking",
            "bakery",
            "gastro",
            "hotel",
            "supplier",
            "distributor",
            "importer",
            "wholesale",
            "food grade",
            "fda",
            "lfgb",
            "pantone",
            "logo",
            "brand",
            "products",
            "sortiment",
            "produkte",
            "vertrieb",
        )
        score += sum(1 for marker in positive_markers if marker in lowered)

        negative_markers = (
            "sale",
            "versand",
            "captcha",
            "widerruf",
            "terms",
            "products & service magazine",
            "contact jobs men",
            "where service begins we are",
            "spot on new items",
            "jetzt entdecken",
        )
        negative_markers += self.NOISE_MARKERS
        score -= sum(2 for marker in negative_markers if marker in lowered)

        parent_hint = self._context_hint(element)
        if any(
            marker in parent_hint
            for marker in (
                "about",
                "company",
                "product",
                "collection",
                "catalog",
                "private",
                "brand",
                "service",
                "hero",
                "content",
            )
        ):
            score += 3
        if any(marker in parent_hint for marker in ("footer", "cookie", "privacy", "cart", "checkout")):
            score -= 3
        return (score, len(text))

    def _context_hint(self, element: Tag) -> str:
        parts: list[str] = []
        parent = element.parent
        steps = 0
        while parent is not None and steps < 3:
            if isinstance(parent, Tag):
                identifier = " ".join(
                    value
                    for value in (
                        parent.get("id", ""),
                        " ".join(parent.get("class", [])),
                    )
                    if value
                )
                parts.append(identifier.lower())
            parent = parent.parent
            steps += 1
        return " ".join(part for part in parts if part)

    def _extract_title(self, html_text: str) -> str:
        if BeautifulSoup:
            soup = BeautifulSoup(html_text, "html.parser")
            return soup.title.get_text(strip=True) if soup.title else ""
        marker_start = html_text.lower().find("<title>")
        marker_end = html_text.lower().find("</title>")
        if marker_start >= 0 and marker_end > marker_start:
            return html_text[marker_start + 7 : marker_end].strip()
        return ""

    def _extract_candidate_links(self, base_url: str, homepage_html: str) -> list[tuple[str, str]]:
        candidates: list[tuple[int, str, str]] = []
        base_domain = urlparse(base_url).netloc
        if BeautifulSoup:
            soup = BeautifulSoup(homepage_html, "html.parser")
            anchors = ((anchor.get("href", ""), anchor.get_text(" ", strip=True)) for anchor in soup.find_all("a", href=True))
        else:
            anchors = self._extract_links_without_parser(homepage_html)

        for href, label in anchors:
            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)
            if parsed.netloc != base_domain:
                continue
            if not parsed.scheme.startswith("http"):
                continue
            score, page_type = self._link_score(label, href)
            if score <= 0:
                continue
            candidates.append((score, absolute, page_type))

        deduped: list[tuple[str, str]] = []
        seen: set[str] = set()
        for _, link, page_type in sorted(candidates, reverse=True):
            normalized = link.rstrip("/")
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append((link, page_type))
        return deduped

    def _link_score(self, label: str, href: str) -> tuple[int, str]:
        text = f"{label} {href}".lower()
        page_type = "page"
        best_score = 0
        for candidate_type, keywords in self.PAGE_TYPE_RULES.items():
            local_score = self.PAGE_TYPE_PRIORITY.get(candidate_type, 1)
            local_score += sum(2 for keyword in keywords if keyword in text)
            if local_score > best_score and any(keyword in text for keyword in keywords):
                best_score = local_score
                page_type = candidate_type
        if any(marker in text for marker in ("privacy", "datenschutz", "cookie", "login", "cart", "checkout")):
            return (0, "page")
        return (best_score, page_type)

    def _extract_meta_description(self, soup: BeautifulSoup) -> str:
        meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
        if not meta:
            meta = soup.find("meta", attrs={"property": re.compile("description", re.I)})
        content = meta.get("content", "").strip() if meta else ""
        return self._normalize_text(content)

    def _normalize_text(self, text: str) -> str:
        cleaned = text.replace("\xa0", " ")
        cleaned = re.sub(r"/\*.*?\*/", " ", cleaned, flags=re.S)
        cleaned = re.sub(r"\.[a-zA-Z0-9_-]+\s*\{[^{}]{0,500}\}", " ", cleaned)
        cleaned = re.sub(r"[a-zA-Z0-9_-]+\s*\{[^{}]{0,500}\}", " ", cleaned)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _looks_like_html_noise(self, text: str) -> bool:
        sample = text[:500].lower()
        html_markers = ("<!doctype", "<html", "<head", "<meta", "<script")
        if any(marker in sample for marker in html_markers):
            return True
        return sample.count("<") > 5 and sample.count(">") > 5

    def _extract_meta_description_raw(self, html_text: str) -> str:
        match = re.search(
            r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\']([^"\']+)["\']',
            html_text,
            flags=re.I,
        )
        if not match:
            match = re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\'](?:description|og:description)["\']',
                html_text,
                flags=re.I,
            )
        return self._normalize_text(html.unescape(match.group(1))) if match else ""

    def _extract_text_without_parser(self, html_text: str) -> str:
        cleaned = re.sub(r"(?is)<script.*?>.*?</script>", " ", html_text)
        cleaned = re.sub(r"(?is)<style.*?>.*?</style>", " ", cleaned)
        cleaned = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", cleaned)
        cleaned = re.sub(r"(?is)<!--.*?-->", " ", cleaned)
        cleaned = re.sub(r"(?is)<svg.*?>.*?</svg>", " ", cleaned)
        cleaned = re.sub(r"(?is)<template.*?>.*?</template>", " ", cleaned)
        cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
        cleaned = html.unescape(cleaned)
        return self._normalize_text(cleaned)

    def _extract_links_without_parser(self, html_text: str) -> list[tuple[str, str]]:
        links: list[tuple[str, str]] = []
        pattern = re.compile(r'(?is)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>')
        for href, inner in pattern.findall(html_text):
            label = self._normalize_text(re.sub(r"(?is)<[^>]+>", " ", inner))
            links.append((href, label))
        return links

    def _prefix_context(self, body_text: str, title: str = "", meta_description: str = "") -> str:
        parts: list[str] = []
        title = self._normalize_text(title)
        meta_description = self._normalize_text(meta_description)
        body_text = self._normalize_text(body_text)
        if title and title.lower() not in body_text.lower():
            parts.append(title)
        if meta_description and meta_description.lower() not in body_text.lower():
            parts.append(meta_description)
        if body_text:
            parts.append(body_text)
        return "\n\n".join(part for part in parts if part).strip()

    def _build_synthetic_snapshot(
        self, website: str, company_name: str, industry: str
    ) -> WebsiteSnapshot:
        domain = urlparse(website).netloc or "example.com"
        support_email = f"sales@{domain.replace('www.', '')}"
        product_line = self._product_line(industry)
        about_text = (
            f"{company_name} is a {industry or 'B2B supplier'} serving commercial buyers "
            f"across Europe. The company focuses on reliable sourcing, project support, "
            f"and distributor relationships."
        )
        products_text = (
            f"Products include {product_line}. The company highlights stable supply, "
            f"private label support, and flexible order planning for distributors."
        )
        contact_text = (
            f"Contact the team via {support_email}. The company works with importers, "
            f"wholesalers, and project-oriented buyers."
        )
        pages = [
            WebsitePage(url=website, title="Home", text=about_text, page_type="home", blocks=[about_text]),
            WebsitePage(
                url=f"{website}/products",
                title="Products",
                text=products_text,
                page_type="products",
                blocks=[products_text],
            ),
            WebsitePage(
                url=f"{website}/contact",
                title="Contact",
                text=contact_text,
                page_type="contact",
                blocks=[contact_text],
            ),
        ]
        combined_text = "\n\n".join(page.text for page in pages)
        return WebsiteSnapshot(
            website=website,
            success=True,
            combined_text=combined_text,
            pages=pages,
            email_candidates=[support_email],
        )

    def _product_line(self, industry: str) -> str:
        industry = (industry or "").lower()
        if "light" in industry or "led" in industry:
            return "LED panel lights, downlights, flood lights, and OEM packaging options"
        if "furniture" in industry:
            return "dining furniture, storage cabinets, and custom project orders"
        if "solar" in industry:
            return "solar panels, mounting kits, and off-grid accessories"
        if "hardware" in industry:
            return "door hardware, hand tools, and project supply bundles"
        return "core B2B product lines, custom orders, and sourcing support"
