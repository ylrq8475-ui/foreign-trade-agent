from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from ai.customer_profile import CustomerProfileGenerator
from ai.email_generator import EmailDraftGenerator
from config.settings import get_settings
from config.statuses import (
    REPLY_STATUS_OPTIONS,
    STATUS_OPTIONS,
    STATUS_REPLIED,
    STATUS_REVIEW,
    STATUS_SENT,
)
from crawler.website_fetcher import WebsiteFetcher
from crawler.website_parser import WebsiteParser
from database.models import coerce_customer_profile
from database.repository import CustomerRepository
from mail.sender import ManualSender, SendValidationError
from maps.google_places import GooglePlacesClient


BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))


CATEGORY_LABELS = {
    "company_positioning": "公司定位",
    "product_range": "产品范围",
    "private_label": "私牌/定制合作",
    "brand_owner": "自有品牌",
    "brand_story": "品牌表达",
    "general": "一般依据",
}

TYPE_LABELS = {
    "fact": "事实",
    "inference": "推断",
}


def _clean_source_text(text: str) -> str:
    replacements = {
        "â": "'",
        "â": "-",
        "â": '"',
        "â": '"',
        "â¦": "...",
    }
    cleaned = str(text or "")
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    return cleaned.strip()


def _basis_explanation_cn(item: dict) -> str:
    quote = _clean_source_text(item.get("quote", ""))
    lowered = quote.lower()
    points: list[str] = []
    if "household" in lowered and "kitchen" in lowered:
        points.append("官网提到这家公司围绕家居和厨房用品开展业务。")
    if "supplier" in lowered or "distributor" in lowered or "importer" in lowered:
        points.append("这条内容更像渠道商或供应型客户信号。")
    if "private label" in lowered or "oem" in lowered:
        points.append("官网公开内容里出现了私牌或定制合作信号。")
    if "hotel" in lowered or "hospitality" in lowered:
        points.append("官网内容显示其业务涉及酒店或餐饮用品方向。")
    if "innovative" in lowered or "innovation" in lowered:
        points.append("官网强调了创新产品或创新定位。")
    if "brand" in lowered and "private label" not in lowered:
        points.append("官网内容里能看出品牌或品牌线索。")
    if "kitchen equipment" in lowered or "kitchen tools" in lowered:
        points.append("官网内容显示其产品覆盖厨房设备或厨房工具。")
    if not points:
        points.append("这条依据来自客户官网公开内容，可作为开发信中的个性化切入点。")
    return " ".join(points)


def build_basis_cards(items: list[dict]) -> list[dict]:
    cards: list[dict] = []
    for item in items or []:
        cards.append(
            {
                "page": item.get("page", ""),
                "quote": _clean_source_text(item.get("quote", "")),
                "type_label": TYPE_LABELS.get(str(item.get("type", "")), "依据"),
                "category_label": CATEGORY_LABELS.get(str(item.get("category", "")), "一般依据"),
                "explanation_cn": _basis_explanation_cn(item),
            }
        )
    return cards


def build_summary_cn(customer: dict) -> str:
    customer_type = str(customer.get("customer_type") or "").strip().lower()
    products = [str(item).strip() for item in (customer.get("main_products") or []) if str(item).strip()]
    text_parts = [
        _clean_source_text(customer.get("website_summary", "")),
        _clean_source_text(customer.get("source_snippet", "")),
        _clean_source_text(customer.get("manual_research_note", "")),
    ]
    profile = customer.get("profile_json") or {}
    for item in profile.get("evidence", []) or []:
        text_parts.append(_clean_source_text(item.get("quote", "")))
    text_blob = " ".join(part for part in text_parts if part).lower()

    role_map = {
        "distributor": "这家公司更像分销商或渠道客户。",
        "importer": "这家公司更像进口商或采购型客户。",
        "brand owner": "这家公司更像自有品牌方。",
        "brand_owner": "这家公司更像自有品牌方。",
        "wholesaler": "这家公司更像批发或渠道型客户。",
        "supplier": "这家公司更像供应与渠道并重的客户。",
        "store": "这家公司更像零售或门店型客户，需要谨慎筛选。",
    }

    parts: list[str] = []
    if customer_type in role_map:
        parts.append(role_map[customer_type])
    elif "distributor" in text_blob or "dropshipping" in text_blob:
        parts.append("官网内容显示它有明显的渠道或分销属性。")
    elif "importer" in text_blob:
        parts.append("官网内容显示它更像进口或采购型客户。")
    elif "brand" in text_blob:
        parts.append("官网内容里能看出一定的品牌属性。")

    if products:
        if len(products) == 1:
            parts.append(f"当前抽取到的核心产品方向是：{products[0]}。")
        else:
            parts.append(f"当前抽取到的产品方向包括：{'、'.join(products[:3])}。")

    if "private label" in text_blob or "oem" in text_blob:
        parts.append("官网公开内容里出现了私牌或定制合作信号，可以考虑从定制配合切入。")
    elif "household" in text_blob and "kitchen" in text_blob:
        parts.append("官网内容主要围绕家居和厨房用品，和日用厨具方向有一定相关性。")
    elif "hotel" in text_blob or "gastronomie" in text_blob or "hospitality" in text_blob:
        parts.append("官网内容偏酒店或餐饮用品渠道，更适合从补充厨房工具品类切入。")

    confidence = customer.get("confidence_score")
    if confidence not in (None, ""):
        try:
            score = float(confidence)
            if score >= 0.8:
                parts.append("当前抽取结果整体可信度较高，但仍建议结合官网页面人工复核。")
            elif score >= 0.6:
                parts.append("当前抽取结果可作为参考，发送前建议重点人工复核。")
            else:
                parts.append("当前抽取结果可信度一般，建议先人工确认再继续生成草稿。")
        except (TypeError, ValueError):
            pass

    if not parts:
        parts.append("当前系统已抓到部分官网公开信息，但还需要你结合原页面再做一次人工判断。")
    return " ".join(parts)


ALLOWED_SEARCH_MODES = {"strict", "balanced", "broad"}


class ApiLeadSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    country: str = Field(min_length=1, max_length=120)
    limit: int = Field(default=5, ge=1, le=20)
    search_mode: str = Field(default="balanced", min_length=1, max_length=20)
    import_to_workspace: bool = False


def serialize_lead(lead: Any, *, customer_id: int | None = None) -> dict[str, Any]:
    return {
        "place_id": str(getattr(lead, "place_id", "") or "").strip(),
        "company_name": str(getattr(lead, "company_name", "") or "").strip(),
        "country": str(getattr(lead, "country", "") or "").strip(),
        "city": str(getattr(lead, "city", "") or "").strip(),
        "address": str(getattr(lead, "address", "") or "").strip(),
        "website": str(getattr(lead, "website", "") or "").strip(),
        "phone": str(getattr(lead, "phone", "") or "").strip(),
        "industry": str(getattr(lead, "industry", "") or "").strip(),
        "search_keyword": str(getattr(lead, "search_keyword", "") or "").strip(),
        "source_platform": str(getattr(lead, "source_platform", "") or "").strip(),
        "customer_id": customer_id,
    }


def create_app() -> FastAPI:
    settings = get_settings()
    repository = CustomerRepository(
        settings.db_path,
        journal_mode=settings.db_journal_mode,
        synchronous=settings.db_synchronous,
    )
    repository.init_db()

    app = FastAPI(title=settings.app_name)
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web" / "static")), name="static")

    app.state.settings = settings
    app.state.repository = repository
    app.state.places = GooglePlacesClient(settings)
    app.state.fetcher = WebsiteFetcher(settings)
    app.state.parser = WebsiteParser()
    app.state.profile_generator = CustomerProfileGenerator(settings)
    app.state.email_generator = EmailDraftGenerator(settings, repository=repository)
    app.state.sender = ManualSender(repository, settings)

    def require_api_token(*required_scopes: str):
        async def dependency(
            request: Request,
            authorization: str | None = Header(default=None),
        ) -> dict[str, Any]:
            header_value = str(authorization or "").strip()
            if not header_value or not header_value.lower().startswith("bearer "):
                raise HTTPException(status_code=401, detail="Missing bearer token")
            raw_token = header_value.split(" ", 1)[1].strip()
            token_meta = repository.authenticate_api_token(raw_token)
            if not token_meta:
                raise HTTPException(status_code=401, detail="Invalid or expired token")
            token_scopes = set(token_meta.get("scopes") or [])
            missing_scopes = [scope for scope in required_scopes if scope not in token_scopes]
            if missing_scopes:
                raise HTTPException(
                    status_code=403,
                    detail=f"Missing required scope: {', '.join(missing_scopes)}",
                )
            request.state.api_token = token_meta
            return token_meta

        return dependency

    def record_api_usage(
        *,
        token_meta: dict[str, Any],
        request: Request,
        status_code: int,
        request_summary: str = "",
    ) -> None:
        try:
            repository.record_api_usage(
                token_id=int(token_meta["id"]),
                path=request.url.path,
                method=request.method,
                status_code=status_code,
                request_summary=request_summary,
            )
        except Exception:
            pass

    @app.get("/")
    async def home() -> RedirectResponse:
        return RedirectResponse("/customers", status_code=303)

    @app.get("/api/v1/health")
    async def api_health() -> dict[str, Any]:
        return {
            "ok": True,
            "service": settings.app_name,
            "api_ready": True,
            "google_places_configured": bool(settings.google_maps_api_key),
            "minimax_configured": bool(settings.minimax_api_key),
        }

    @app.get("/api/v1/tokens/me")
    async def api_token_me(
        request: Request,
        token_meta: dict[str, Any] = Depends(require_api_token()),
    ) -> dict[str, Any]:
        try:
            return {
                "token": {
                    "id": token_meta.get("id"),
                    "name": token_meta.get("token_name"),
                    "status": token_meta.get("status"),
                    "scopes": token_meta.get("scopes") or [],
                    "token_prefix": token_meta.get("token_prefix"),
                    "expires_at": token_meta.get("expires_at"),
                    "last_used_at": token_meta.get("last_used_at"),
                }
            }
        finally:
            record_api_usage(
                token_meta=token_meta,
                request=request,
                status_code=200,
                request_summary="self-introspection",
            )

    @app.post("/api/v1/leads/search")
    async def api_search_leads(
        payload: ApiLeadSearchRequest,
        request: Request,
        token_meta: dict[str, Any] = Depends(require_api_token("leads:search")),
    ) -> dict[str, Any]:
        status_code = 200
        request_summary = json.dumps(
            {
                "query": payload.query,
                "country": payload.country,
                "limit": payload.limit,
                "search_mode": payload.search_mode,
                "import_to_workspace": payload.import_to_workspace,
            },
            ensure_ascii=False,
        )
        try:
            search_mode = payload.search_mode.strip().lower()
            if search_mode not in ALLOWED_SEARCH_MODES:
                raise HTTPException(
                    status_code=422,
                    detail="Unsupported search_mode. Use strict, balanced, or broad.",
                )
            token_scopes = set(token_meta.get("scopes") or [])
            if payload.import_to_workspace and "customers:import" not in token_scopes:
                raise HTTPException(status_code=403, detail="Missing required scope: customers:import")

            leads = app.state.places.search_leads(
                query=payload.query.strip(),
                country=payload.country.strip(),
                limit=payload.limit,
                search_mode=search_mode,
            )
            imported_count = 0
            items: list[dict[str, Any]] = []
            for lead in leads:
                customer_id: int | None = None
                if payload.import_to_workspace:
                    customer_id = repository.upsert_lead(lead)
                    imported_count += 1
                items.append(serialize_lead(lead, customer_id=customer_id))

            return {
                "query": payload.query.strip(),
                "country": payload.country.strip(),
                "search_mode": search_mode,
                "count": len(items),
                "imported_count": imported_count,
                "items": items,
            }
        except HTTPException as exc:
            status_code = exc.status_code
            raise
        except Exception as exc:
            status_code = 500
            raise HTTPException(status_code=500, detail=f"Lead search failed: {type(exc).__name__}") from exc
        finally:
            record_api_usage(
                token_meta=token_meta,
                request=request,
                status_code=status_code,
                request_summary=request_summary,
            )

    @app.post("/api/v1/customers/{customer_id}/analyze")
    async def api_analyze_customer(
        customer_id: int,
        request: Request,
        token_meta: dict[str, Any] = Depends(require_api_token("customers:analyze")),
    ) -> dict[str, Any]:
        status_code = 200
        request_summary = json.dumps({"customer_id": customer_id}, ensure_ascii=False)
        try:
            customer = repository.get_customer(customer_id)
            if not customer:
                raise HTTPException(status_code=404, detail="Customer not found")

            snapshot = app.state.fetcher.fetch(
                customer.get("website", ""),
                company_name=customer.get("company_name", ""),
                industry=customer.get("industry", ""),
            )
            parsed = app.state.parser.parse(snapshot, fallback_industry=customer.get("industry", ""))
            profile = app.state.profile_generator.generate(customer, parsed)
            draft = app.state.email_generator.generate(customer, profile)
            repository.save_analysis(
                customer_id,
                parsed,
                profile,
                draft,
                snapshot=snapshot,
                email_candidates=snapshot.email_candidates,
            )
            refreshed = repository.get_customer(customer_id) or customer
            return {
                "customer_id": customer_id,
                "company_name": refreshed.get("company_name", ""),
                "status": refreshed.get("status", ""),
                "contact_email": refreshed.get("contact_email", ""),
                "customer_type": refreshed.get("customer_type", ""),
                "main_products": refreshed.get("main_products", []),
                "draft_subject": refreshed.get("email_subject", ""),
                "draft_review_status": refreshed.get("draft_review_status", ""),
                "review_required": bool(refreshed.get("review_required")),
            }
        except HTTPException as exc:
            status_code = exc.status_code
            raise
        except Exception as exc:
            status_code = 500
            raise HTTPException(status_code=500, detail=f"Customer analysis failed: {type(exc).__name__}") from exc
        finally:
            record_api_usage(
                token_meta=token_meta,
                request=request,
                status_code=status_code,
                request_summary=request_summary,
            )

    @app.get("/customers")
    async def customers(request: Request):
        search_form = {
            "query": request.query_params.get("draft_query", "kitchen tools distributor"),
            "country": request.query_params.get("draft_country", "Germany"),
            "limit": request.query_params.get("draft_limit", "5"),
            "mode": request.query_params.get("draft_mode", "balanced"),
        }
        filters = {
            "status": request.query_params.get("status", ""),
            "country": request.query_params.get("country", ""),
            "keyword": request.query_params.get("keyword", ""),
            "search": request.query_params.get("search", ""),
            "tag": request.query_params.get("tag", ""),
        }
        rows = repository.list_customers(**filters)
        stats = {
            "total": len(rows),
            "review": sum(1 for row in rows if row.get("status") == STATUS_REVIEW),
            "sent": sum(1 for row in rows if row.get("status") == STATUS_SENT),
            "replied": sum(1 for row in rows if row.get("status") == STATUS_REPLIED),
        }
        return templates.TemplateResponse(
            request,
            "customers.html",
            {
                "customers": rows,
                "stats": stats,
                "google_status": app.state.places.status_summary(),
                "minimax_status": app.state.profile_generator.client.status_summary(),
                "smtp_status": app.state.sender.status_summary(),
                "saved_searches": repository.list_saved_searches(),
                "search_form": search_form,
                "status_options": STATUS_OPTIONS,
                "filters": filters,
                "current_nav": "workspace",
                "settings": settings,
            },
        )

    @app.post("/customers/discover")
    async def discover_customers(
        query: str = Form(...),
        country: str = Form(...),
        limit: int = Form(5),
        search_mode: str = Form("balanced"),
    ) -> RedirectResponse:
        leads = app.state.places.search_leads(
            query=query,
            country=country,
            limit=limit,
            search_mode=search_mode,
        )
        for lead in leads:
            customer_id = repository.upsert_lead(lead)
            if lead.website:
                customer = repository.get_customer(customer_id)
                if not customer:
                    continue
                snapshot = app.state.fetcher.fetch(
                    customer.get("website", ""),
                    company_name=customer.get("company_name", ""),
                    industry=customer.get("industry", ""),
                )
                parsed = app.state.parser.parse(snapshot, fallback_industry=customer.get("industry", ""))
                profile = app.state.profile_generator.generate(customer, parsed)
                draft = app.state.email_generator.generate(customer, profile)
                repository.save_analysis(
                    customer_id,
                    parsed,
                    profile,
                    draft,
                    snapshot=snapshot,
                    email_candidates=snapshot.email_candidates,
                )
        redirect_url = "/customers?" + urlencode(
            {
                "draft_query": query,
                "draft_country": country,
                "draft_limit": limit,
                "draft_mode": search_mode,
            }
        )
        return RedirectResponse(redirect_url, status_code=303)

    @app.post("/saved-searches")
    async def save_saved_search(
        query: str = Form(...),
        country: str = Form(...),
        limit: int = Form(5),
        search_mode: str = Form("balanced"),
        note: str = Form(""),
    ) -> RedirectResponse:
        repository.save_saved_search(
            query=query,
            country=country,
            limit=limit,
            search_mode=search_mode,
            note=note,
        )
        return RedirectResponse("/customers", status_code=303)

    @app.post("/saved-searches/{saved_search_id}/delete")
    async def delete_saved_search(saved_search_id: int) -> RedirectResponse:
        repository.delete_saved_search(saved_search_id)
        return RedirectResponse("/customers", status_code=303)

    @app.get("/customers/{customer_id}")
    async def customer_detail(request: Request, customer_id: int):
        customer = repository.get_customer(customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        return templates.TemplateResponse(
            request,
            "customer_detail.html",
            {
                "customer": customer,
                "basis_cards": build_basis_cards(customer.get("email_basis") or []),
                "website_summary_cn": build_summary_cn(customer),
                "status_options": STATUS_OPTIONS,
                "reply_status_options": REPLY_STATUS_OPTIONS,
                "current_nav": "workspace",
                "settings": settings,
            },
        )

    @app.post("/customers/{customer_id}/analyze")
    async def analyze_customer(customer_id: int) -> RedirectResponse:
        customer = repository.get_customer(customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        snapshot = app.state.fetcher.fetch(
            customer.get("website", ""),
            company_name=customer.get("company_name", ""),
            industry=customer.get("industry", ""),
        )
        parsed = app.state.parser.parse(snapshot, fallback_industry=customer.get("industry", ""))
        profile = app.state.profile_generator.generate(customer, parsed)
        draft = app.state.email_generator.generate(customer, profile)
        repository.save_analysis(
            customer_id,
            parsed,
            profile,
            draft,
            snapshot=snapshot,
            email_candidates=snapshot.email_candidates,
        )
        return RedirectResponse(f"/customers/{customer_id}", status_code=303)

    @app.post("/customers/{customer_id}/status")
    async def update_status(customer_id: int, status: str = Form(...)) -> RedirectResponse:
        repository.update_status(customer_id, status)
        return RedirectResponse(f"/customers/{customer_id}", status_code=303)

    @app.post("/customers/{customer_id}/note")
    async def update_note(customer_id: int, note: str = Form("")) -> RedirectResponse:
        repository.update_note(customer_id, note)
        return RedirectResponse(f"/customers/{customer_id}", status_code=303)

    @app.post("/customers/{customer_id}/contact-email")
    async def update_contact_email(
        customer_id: int,
        contact_email: str = Form(""),
    ) -> RedirectResponse:
        repository.update_contact_email(customer_id, contact_email)
        return RedirectResponse(f"/customers/{customer_id}", status_code=303)

    @app.post("/customers/{customer_id}/manual-note")
    async def update_manual_note(
        customer_id: int,
        manual_research_note: str = Form(""),
    ) -> RedirectResponse:
        repository.update_manual_research_note(customer_id, manual_research_note)
        return RedirectResponse(f"/customers/{customer_id}", status_code=303)

    @app.post("/customers/{customer_id}/tags")
    async def update_tags(
        customer_id: int,
        tags_text: str = Form(""),
    ) -> RedirectResponse:
        repository.update_tags(customer_id, tags_text)
        return RedirectResponse(f"/customers/{customer_id}", status_code=303)

    @app.post("/customers/{customer_id}/draft")
    async def update_draft(
        customer_id: int,
        subject: str = Form(""),
        body: str = Form(""),
        review_note: str = Form(""),
    ) -> RedirectResponse:
        customer = repository.get_customer(customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        profile = coerce_customer_profile(customer.get("profile_json") or customer)
        reviewed_draft, merged_review_note, _issues = app.state.email_generator.review_manual_draft(
            customer,
            profile,
            subject=subject,
            body=body,
            review_note=review_note,
        )
        repository.update_draft(
            customer_id,
            reviewed_draft.subject,
            reviewed_draft.body,
            merged_review_note,
            ai_tone_risk=reviewed_draft.ai_tone_risk,
        )
        return RedirectResponse(f"/customers/{customer_id}", status_code=303)

    @app.post("/customers/{customer_id}/approve")
    async def approve_draft(
        customer_id: int,
        review_note: str = Form(""),
    ) -> RedirectResponse:
        repository.approve_draft(customer_id, review_note)
        if app.state.sender.status_summary().get("auto_send_on_approval"):
            customer = repository.get_customer(customer_id) or {}
            recipient_email = str(customer.get("contact_email") or "").strip()
            if recipient_email:
                try:
                    app.state.sender.send(customer_id, recipient_email)
                except SendValidationError as exc:
                    prior_note = customer.get("note", "")
                    repository.update_note(
                        customer_id,
                        f"{prior_note}\n[Auto Send Error] {exc}".strip(),
                    )
        return RedirectResponse(f"/customers/{customer_id}", status_code=303)

    @app.post("/customers/{customer_id}/reply")
    async def record_reply(
        customer_id: int,
        reply_status: str = Form(""),
        reply_note: str = Form(""),
    ) -> RedirectResponse:
        if reply_status:
            repository.record_reply_outcome(
                customer_id,
                reply_status=reply_status,
                note=reply_note,
            )
        return RedirectResponse(f"/customers/{customer_id}", status_code=303)

    @app.post("/customers/{customer_id}/send")
    async def send_email(
        customer_id: int,
        recipient_email: str = Form(""),
    ) -> RedirectResponse:
        try:
            app.state.sender.send(customer_id, recipient_email)
        except SendValidationError as exc:
            customer = repository.get_customer(customer_id) or {}
            prior_note = customer.get("note", "")
            repository.update_note(
                customer_id,
                f"{prior_note}\n[Send Error] {exc}".strip(),
            )
        return RedirectResponse(f"/customers/{customer_id}", status_code=303)

    @app.post("/customers/{customer_id}/delete")
    async def delete_customer(customer_id: int) -> RedirectResponse:
        repository.delete_customer(customer_id)
        return RedirectResponse("/customers", status_code=303)

    return app


app = create_app()
