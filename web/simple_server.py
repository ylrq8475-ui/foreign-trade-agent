from __future__ import annotations

import html
import json
import secrets
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlencode, urlparse

from ai.customer_profile import CustomerProfileGenerator
from ai.email_generator import EmailDraftGenerator
from config.settings import Settings, get_settings, reload_runtime_settings, save_runtime_env
from config.statuses import (
    REPLY_STATUS_OPTIONS,
    STATUS_INVALID,
    STATUS_NEW,
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


STATUS_ALIASES = {
    "鏈仈绯?": "未联系",
    "宸茬敓鎴愬紑鍙戜俊": "已生成开发信",
    "寰呬汉宸ュ鏍?": "待人工审核",
    "宸插彂閫?": "已发送",
    "宸插洖澶?": "已回复",
    "璺熻繘涓?": "跟进中",
    "鏃犳晥瀹㈡埛": "无效客户",
    "宸叉垚浜?": "已成交",
    "瀹㈡埛宸插洖澶?": "客户已回复",
    "鑷姩鍥炲": "自动回复",
    "閭欢閫€淇?": "邮件退信",
    "鎷掔粷娌熼€?": "拒绝沟通",
}

ACTION_ALIASES = {
    "鐘舵€佸彉鏇?": "状态变更",
    "澶囨敞鏇存柊": "备注更新",
    "鏀朵欢浜烘洿鏂?": "收件人更新",
    "浜哄伐鐗瑰緛鏇存柊": "人工特征更新",
    "鏍囩鏇存柊": "标签更新",
    "鑽夌鏇存柊": "草稿更新",
    "鑽夌瀹℃牳閫氳繃": "草稿审核通过",
    "鍥炲缁撴灉鍥炲啓": "回复结果回写",
    "绾跨储瀵煎叆": "线索导入",
    "瀹樼綉鍒嗘瀽瀹屾垚": "官网分析完成",
    "瀹樼綉鎶撳彇瀹屾垚": "官网抓取完成",
    "鍙戦€佽褰?": "发送记录",
    "鍒犻櫎瀹㈡埛": "删除客户",
}


class SimpleAppContext:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repository = CustomerRepository(
            settings.db_path,
            journal_mode=settings.db_journal_mode,
            synchronous=settings.db_synchronous,
        )
        self.repository.init_db()
        self.places = GooglePlacesClient(settings)
        self.fetcher = WebsiteFetcher(settings)
        self.parser = WebsiteParser()
        self.profile_generator = CustomerProfileGenerator(settings)
        self.email_generator = EmailDraftGenerator(settings)
        self.sender = ManualSender(self.repository, settings)
        self.admin_sessions: set[str] = set()

    def refresh_runtime_configuration(self) -> None:
        self.settings = reload_runtime_settings()
        self.places = GooglePlacesClient(self.settings)
        self.fetcher = WebsiteFetcher(self.settings)
        self.profile_generator = CustomerProfileGenerator(self.settings)
        self.email_generator = EmailDraftGenerator(self.settings)
        self.sender = ManualSender(self.repository, self.settings)

    def setup_status(self) -> dict[str, bool]:
        smtp = self.sender.status_summary()
        admin_password = self.settings.admin_password.strip()
        return {
            "google_maps_ready": bool(self.settings.google_maps_api_key.strip()),
            "admin_ready": bool(
                self.settings.admin_username.strip()
                and admin_password
                and admin_password != "change-me-admin"
            ),
            "company_ready": bool(
                self.settings.your_company_name.strip()
                and self.settings.your_company_name.strip() != "Your Company"
            ),
            "smtp_ready": bool(smtp.get("configured")),
        }

    def setup_required(self) -> bool:
        status = self.setup_status()
        return not status["google_maps_ready"] or not status["admin_ready"]

    def verify_admin_credentials(self, username: str, password: str) -> bool:
        return (
            username.strip() == self.settings.admin_username
            and password == self.settings.admin_password
        )

    def create_admin_session(self) -> str:
        token = secrets.token_urlsafe(24)
        self.admin_sessions.add(token)
        return token

    def has_admin_session(self, token: str) -> bool:
        return bool(token and token in self.admin_sessions)

    def remove_admin_session(self, token: str) -> None:
        if token:
            self.admin_sessions.discard(token)


class SimpleMVPHandler(BaseHTTPRequestHandler):
    server_version = "MVPHTTP/0.6"

    @property
    def ctx(self) -> SimpleAppContext:
        return self.server.context  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        if path == "/setup":
            self._render_setup(parse_qs(parsed_url.query))
            return
        if self.ctx.setup_required():
            self._redirect("/setup")
            return
        if path == "/admin/login":
            self._render_admin_login(parse_qs(parsed_url.query))
            return
        if path == "/admin/settings/email":
            if not self._require_admin(path):
                return
            self._render_admin_email_settings(parse_qs(parsed_url.query))
            return
        if path in ("/", "/customers"):
            self._render_customers(parse_qs(parsed_url.query))
            return
        if path.startswith("/customers/"):
            customer_id = self._extract_customer_id(path)
            if customer_id is None:
                self._not_found()
                return
            self._render_customer_detail(customer_id)
            return
        self._not_found()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        data = self._read_form_data()
        if path == "/setup":
            self._handle_setup_submit(data)
            return
        if self.ctx.setup_required():
            self._redirect("/setup")
            return

        if path == "/admin/login":
            username = data.get("username", [""])[0]
            password = data.get("password", [""])[0]
            next_path = data.get("next", ["/admin/settings/email"])[0] or "/admin/settings/email"
            if self.ctx.verify_admin_credentials(username, password):
                token = self.ctx.create_admin_session()
                self._redirect(next_path, cookies={"admin_session": token})
                return
            self._redirect(
                "/admin/login?"
                + urlencode(
                    {
                        "notice": "管理员账号或密码不正确。",
                        "notice_type": "warning",
                        "next": next_path,
                    }
                )
            )
            return

        if path == "/admin/logout":
            token = self._cookie_value("admin_session")
            self.ctx.remove_admin_session(token)
            self._redirect("/admin/login?notice=已退出管理员登录。", cookies={"admin_session": ""})
            return

        if path == "/admin/settings/email":
            if not self._require_admin(path):
                return
            intent = data.get("intent", ["save"])[0] or "save"
            smtp_payload = self._smtp_payload_from_form(data)
            if intent == "test":
                try:
                    self.ctx.sender.test_connection(smtp_payload)
                except Exception as exc:
                    self._redirect(
                        "/admin/settings/email?"
                        + urlencode(
                            {
                                "notice": f"SMTP 测试失败：{type(exc).__name__}: {exc}",
                                "notice_type": "warning",
                            }
                        )
                    )
                    return
                self._redirect(
                    "/admin/settings/email?"
                    + urlencode(
                        {
                            "notice": "SMTP 连接测试成功。",
                            "notice_type": "success",
                        }
                    )
                )
                return

            self.ctx.repository.save_smtp_settings(**smtp_payload)
            self._redirect(
                "/admin/settings/email?"
                + urlencode(
                    {
                        "notice": "SMTP 设置已保存。",
                        "notice_type": "success",
                    }
                )
            )
            return

        if path == "/customers/discover":
            query = data.get("query", [""])[0]
            country = data.get("country", [""])[0]
            limit = int(data.get("limit", ["5"])[0] or 5)
            search_mode = data.get("search_mode", ["balanced"])[0] or "balanced"
            leads = self.ctx.places.search_leads(
                query=query,
                country=country,
                limit=limit,
                search_mode=search_mode,
            )
            analyzed = 0
            for lead in leads:
                customer_id = self.ctx.repository.upsert_lead(lead)
                if lead.website:
                    self._analyze_customer(customer_id)
                    analyzed += 1
            if leads:
                notice = (
                    f"本次找到 {len(leads)} 条客户，已导入 {len(leads)} 条，"
                    f"其中 {analyzed} 条已自动完成官网分析。"
                )
                notice_type = "success"
            else:
                notice = "本次没有找到符合当前筛选规则的客户，建议换更宽一点的关键词，或参考搜索建议重新搜索。"
                notice_type = "warning"
            redirect_url = (
                "/customers"
                f"?draft_query={quote_plus(query)}"
                f"&draft_country={quote_plus(country)}"
                f"&draft_limit={quote_plus(str(limit))}"
                f"&draft_mode={quote_plus(search_mode)}"
                f"&notice={quote_plus(notice)}"
                f"&notice_type={quote_plus(notice_type)}"
            )
            self._redirect(redirect_url)
            return

        if path == "/saved-searches":
            query = data.get("query", [""])[0]
            country = data.get("country", [""])[0]
            limit = int(data.get("limit", ["5"])[0] or 5)
            search_mode = data.get("search_mode", ["balanced"])[0] or "balanced"
            note = data.get("note", [""])[0]
            self.ctx.repository.save_saved_search(
                query=query,
                country=country,
                limit=limit,
                search_mode=search_mode,
                note=note,
            )
            self._redirect("/customers")
            return

        if path.startswith("/saved-searches/") and path.endswith("/delete"):
            parts = [part for part in path.split("/") if part]
            try:
                saved_search_id = int(parts[1])
            except (IndexError, ValueError):
                self._not_found()
                return
            self.ctx.repository.delete_saved_search(saved_search_id)
            self._redirect("/customers")
            return

        if path.startswith("/customers/"):
            customer_id = self._extract_customer_id(path)
            if customer_id is None:
                self._not_found()
                return

            if path.endswith("/analyze"):
                self._analyze_customer(customer_id)
                self._redirect(f"/customers/{customer_id}")
                return
            if path.endswith("/status"):
                status = data.get("status", [STATUS_NEW])[0]
                self.ctx.repository.update_status(customer_id, status)
                self._redirect(f"/customers/{customer_id}")
                return
            if path.endswith("/draft"):
                subject = data.get("subject", [""])[0]
                body = data.get("body", [""])[0]
                review_note = data.get("review_note", [""])[0]
                customer = self.ctx.repository.get_customer(customer_id)
                if not customer:
                    self._not_found()
                    return
                profile = coerce_customer_profile(customer.get("profile_json") or customer)
                reviewed_draft, merged_review_note, _issues = self.ctx.email_generator.review_manual_draft(
                    customer,
                    profile,
                    subject=subject,
                    body=body,
                    review_note=review_note,
                )
                self.ctx.repository.update_draft(
                    customer_id,
                    reviewed_draft.subject,
                    reviewed_draft.body,
                    merged_review_note,
                    ai_tone_risk=reviewed_draft.ai_tone_risk,
                )
                self._redirect(f"/customers/{customer_id}")
                return
            if path.endswith("/approve"):
                review_note = data.get("review_note", [""])[0]
                self.ctx.repository.approve_draft(customer_id, review_note)
                if self.ctx.sender.status_summary().get("auto_send_on_approval"):
                    customer = self.ctx.repository.get_customer(customer_id) or {}
                    recipient_email = str(customer.get("contact_email") or "").strip()
                    if recipient_email:
                        self._attempt_send(
                            customer_id,
                            recipient_email,
                            error_prefix="Auto Send Error",
                        )
                self._redirect(f"/customers/{customer_id}")
                return
            if path.endswith("/approve-send"):
                review_note = data.get("review_note", [""])[0]
                recipient_email = data.get("recipient_email", [""])[0].strip()
                self.ctx.repository.approve_draft(customer_id, review_note)
                if recipient_email:
                    self.ctx.repository.update_contact_email(customer_id, recipient_email)
                customer = self.ctx.repository.get_customer(customer_id) or {}
                target_email = str(customer.get("contact_email") or "").strip()
                if target_email:
                    self._attempt_send(
                        customer_id,
                        target_email,
                        error_prefix="Approve Then Send Error",
                    )
                else:
                    prior_note = customer.get("note", "")
                    error_line = "[Approve Then Send Error] Missing recipient email."
                    merged_note = f"{prior_note}\n{error_line}".strip() if prior_note else error_line
                    self.ctx.repository.update_note(customer_id, merged_note)
                self._redirect(f"/customers/{customer_id}")
                return
            if path.endswith("/note"):
                note = data.get("note", [""])[0]
                self.ctx.repository.update_note(customer_id, note)
                self._redirect(f"/customers/{customer_id}")
                return
            if path.endswith("/contact-email"):
                contact_email = data.get("contact_email", [""])[0]
                self.ctx.repository.update_contact_email(customer_id, contact_email)
                self._redirect(f"/customers/{customer_id}")
                return
            if path.endswith("/manual-note"):
                manual_research_note = data.get("manual_research_note", [""])[0]
                self.ctx.repository.update_manual_research_note(customer_id, manual_research_note)
                self._redirect(f"/customers/{customer_id}")
                return
            if path.endswith("/tags"):
                tags_text = data.get("tags_text", [""])[0]
                self.ctx.repository.update_tags(customer_id, tags_text)
                self._redirect(f"/customers/{customer_id}")
                return
            if path.endswith("/reply"):
                reply_status = data.get("reply_status", [""])[0]
                reply_note = data.get("reply_note", [""])[0]
                if reply_status:
                    self.ctx.repository.record_reply_outcome(
                        customer_id,
                        reply_status=reply_status,
                        note=reply_note,
                    )
                self._redirect(f"/customers/{customer_id}")
                return
            if path.endswith("/send"):
                recipient_email = data.get("recipient_email", [""])[0]
                self._attempt_send(
                    customer_id,
                    recipient_email,
                    error_prefix="Send Error",
                )
                self._redirect(f"/customers/{customer_id}")
                return
            if path.endswith("/delete"):
                self.ctx.repository.delete_customer(customer_id)
                self._redirect("/customers")
                return

        self._not_found()

    def _attempt_send(self, customer_id: int, recipient_email: str, *, error_prefix: str) -> None:
        try:
            self.ctx.sender.send(customer_id, recipient_email)
        except SendValidationError as exc:
            customer = self.ctx.repository.get_customer(customer_id) or {}
            prior_note = customer.get("note", "")
            error_line = f"[{error_prefix}] {exc}"
            merged_note = f"{prior_note}\n{error_line}".strip() if prior_note else error_line
            self.ctx.repository.update_note(customer_id, merged_note)

    def _render_customers(self, query: dict[str, list[str]]) -> None:
        search_form = {
            "query": query.get("draft_query", ["kitchen tools distributor"])[0],
            "country": query.get("draft_country", ["Germany"])[0],
            "limit": query.get("draft_limit", ["5"])[0],
            "mode": query.get("draft_mode", ["balanced"])[0],
        }
        filters = {
            "status": query.get("status", [""])[0],
            "country": query.get("country", [""])[0],
            "keyword": query.get("keyword", [""])[0],
            "search": query.get("search", [""])[0],
            "tag": query.get("tag", [""])[0],
        }
        notice = query.get("notice", [""])[0]
        notice_type = query.get("notice_type", ["info"])[0]
        customers = self.ctx.repository.list_customers(**filters)
        stats = {
            "total": len(customers),
            "review": sum(1 for row in customers if self._label(row.get("status")) == STATUS_REVIEW),
            "sent": sum(1 for row in customers if self._label(row.get("status")) == STATUS_SENT),
            "replied": sum(1 for row in customers if self._label(row.get("status")) == STATUS_REPLIED),
        }
        google_status = self.ctx.places.status_summary()
        minimax_status = self.ctx.profile_generator.client.status_summary()
        smtp_status = self.ctx.sender.status_summary()
        saved_searches = self.ctx.repository.list_saved_searches()
        notice_html = ""
        if notice:
            notice_class = "warning" if notice_type == "warning" else "success"
            notice_html = f"<section class='panel notice {notice_class}'><p>{self._esc(notice)}</p></section>"

        rows: list[str] = []
        for customer in customers:
            tag_text = ", ".join(self._label(tag) for tag in (customer.get("customer_tags") or []))
            company_intro = self._company_intro_cn(customer)
            match_level = customer.get("match_level") or "-"
            match_score = customer.get("match_score")
            match_text = (
                f"{match_level} / {match_score}分"
                if match_score not in (None, "")
                else str(match_level)
            )
            actions = [f'<a href="/customers/{customer["id"]}">进入窗口</a>']
            if self._label(customer.get("status")) == STATUS_INVALID:
                actions.append(
                    f"""
                    <form method="post" action="/customers/{customer['id']}/delete" class="inline-form" onsubmit="return confirm('确认删除这个无效客户吗？');">
                        <button type="submit" class="link-button danger-text">删除</button>
                    </form>
                    """
                )
            rows.append(
                f"""
                <tr>
                    <td>
                        <strong>{self._esc(customer['company_name'])}</strong><br>
                        <small>{self._esc(company_intro)}</small>
                    </td>
                    <td>{self._esc(customer.get('country') or '-')}</td>
                    <td>{self._render_link(customer.get('website') or '')}</td>
                    <td>{self._esc(self._label(customer.get('customer_type') or customer.get('industry') or '-'))}</td>
                    <td><span class="pill">{self._esc(self._label(customer.get('status') or '-'))}</span></td>
                    <td>{self._esc(tag_text or '-')}</td>
                    <td>{self._esc(match_text)}</td>
                    <td>{''.join(actions)}</td>
                </tr>
                """
            )

        saved_search_cards: list[str] = []
        for item in saved_searches:
            refill_link = (
                "/customers"
                f"?draft_query={quote_plus(str(item.get('query', '')))}"
                f"&draft_country={quote_plus(str(item.get('country', '')))}"
                f"&draft_limit={quote_plus(str(item.get('limit', '5')))}"
                f"&draft_mode={quote_plus(str(item.get('search_mode', 'balanced')))}"
            )
            saved_search_cards.append(
                f"""
                <div class="compact-item">
                    <strong>{self._esc(item.get('query', '-'))}</strong>
                    <span>{self._esc(item.get('country', '-'))} / 数量 {self._esc(item.get('limit', '-'))}</span>
                    <small>{self._esc(item.get('note') or '-')}</small>
                    <p><a href="{refill_link}">回填到搜索框</a></p>
                    <form method="post" action="/saved-searches/{int(item.get('id', 0))}/delete" class="inline-form" onsubmit="return confirm('确认删除这个常用搜索词吗？');">
                        <button type="submit" class="link-button danger-text">删除</button>
                    </form>
                </div>
                """
            )
        if not saved_search_cards:
            saved_search_cards.append("<div class='compact-item'><span>还没有保存常用搜索词。</span></div>")

        status_options_html = "".join(
            f'<option value="{self._esc(status)}"{" selected" if filters["status"] == status else ""}>{self._esc(status)}</option>'
            for status in STATUS_OPTIONS
        )

        content = f"""
        {self._page_open("客户开发工作台")}
        <section class="hero">
            <div>
                <p class="eyebrow">Fallback Console</p>
                <h1>客户开发工作台</h1>
                <p class="subtitle">在一个窗口内完成线索导入、客户筛选、状态查看和后续跟进行动。</p>
            </div>
        </section>
        {notice_html}
        <section class="panel full">
            <div class="stats">
                <article><span>客户总数</span><strong>{stats['total']}</strong></article>
                <article><span>待人工审核</span><strong>{stats['review']}</strong></article>
                <article><span>已发送</span><strong>{stats['sent']}</strong></article>
                <article><span>已回复</span><strong>{stats['replied']}</strong></article>
            </div>
        </section>
        <section class="detail-grid">
            <article class="panel">
                <div id="new-search" class="anchor-target"></div>
                <h2>搜索新客户</h2>
                <p>直接在网站内输入关键词、国家和数量，系统会先调用 Google Places 搜索，再把更符合你当前产品线和专业供应商定位的客户写入客户库。</p>
                <form method="post" action="/customers/discover" class="grid">
                    <label><span>关键词</span><input name="query" value="{self._esc(search_form['query'])}"></label>
                    <label><span>国家</span><input name="country" value="{self._esc(search_form['country'])}"></label>
                    <label><span>数量</span><input name="limit" type="number" min="1" max="20" value="{self._esc(search_form['limit'])}"></label>
                    <label><span>搜索模式</span>
                        <select name="search_mode">
                            <option value="strict"{' selected' if search_form['mode']=='strict' else ''}>严格</option>
                            <option value="balanced"{' selected' if search_form['mode']=='balanced' else ''}>平衡</option>
                            <option value="broad"{' selected' if search_form['mode']=='broad' else ''}>宽松</option>
                        </select>
                    </label>
                    <button type="submit">搜索并导入客户</button>
                </form>
            </article>
            <article class="panel">
                <h2>搜索建议</h2>
                <p><strong>推荐词：</strong>silicone kitchenware distributor / silicone kitchen tools importer / food-grade silicone kitchenware wholesaler / private label silicone kitchen tools / baking tools importer / housewares distributor</p>
                <p><strong>优先顺序：</strong>先测 distributor / importer / wholesaler，再测 private label / OEM 方向，最后再扩到 broader housewares。</p>
                <p><strong>避免词：</strong>kitchen shop / retail store / commercial equipment / grossküchentechnik / gastronomiebedarf</p>
                <p><strong>模式建议：</strong>默认先用“平衡”，结果太少时切到“宽松”，要做高精度筛选时再用“严格”。</p>
            </article>
            <article class="panel">
                <h2>常用搜索词</h2>
                <form method="post" action="/saved-searches" class="stack">
                    <label><span>关键词</span><input name="query" value="{self._esc(search_form['query'])}" required></label>
                    <label><span>国家</span><input name="country" value="{self._esc(search_form['country'])}" required></label>
                    <label><span>数量</span><input name="limit" type="number" min="1" max="20" value="{self._esc(search_form['limit'])}"></label>
                    <label><span>搜索模式</span>
                        <select name="search_mode">
                            <option value="strict"{' selected' if search_form['mode']=='strict' else ''}>严格</option>
                            <option value="balanced"{' selected' if search_form['mode']=='balanced' else ''}>平衡</option>
                            <option value="broad"{' selected' if search_form['mode']=='broad' else ''}>宽松</option>
                        </select>
                    </label>
                    <label><span>备注</span><input name="note" placeholder="例如：德国硅胶厨具渠道词"></label>
                    <button type="submit">保存常用搜索词</button>
                </form>
                <div class="compact-list" style="margin-top:12px;">{''.join(saved_search_cards)}</div>
            </article>
            <article class="panel">
                <h2>集成状态</h2>
                <p><strong>Google Places：</strong>{self._esc(google_status.get('mode', '-'))}</p>
                <p><strong>Google 最近状态：</strong>{self._esc(google_status.get('last_error') or '最近一次请求正常')}</p>
                <p><strong>MiniMax 模型：</strong>{self._esc(minimax_status.get('model') or '-')}</p>
                <p><strong>MiniMax 最近状态：</strong>{self._esc(minimax_status.get('last_error') or '最近一次请求正常')}</p>
                <p><strong>SMTP 已配置：</strong>{'是' if smtp_status.get('configured') else '否'}</p>
                <p><strong>SMTP 服务器：</strong>{self._esc(smtp_status.get('host') or '-')}:{self._esc(str(smtp_status.get('port') or '-'))}</p>
                <p><strong>SMTP 模式：</strong>{self._esc(smtp_status.get('security') or '-')}</p>
                <p><strong>审核后自动发送：</strong>{'开启' if smtp_status.get('auto_send_on_approval') else '关闭'}</p>
            </article>
            <article class="panel full">
                <h2>筛选客户</h2>
                <form method="get" action="/customers" class="grid">
                    <label><span>状态</span><select name="status"><option value="">全部</option>{status_options_html}</select></label>
                    <label><span>国家</span><input name="country" value="{self._esc(filters['country'])}" placeholder="Germany"></label>
                    <label><span>关键词</span><input name="keyword" value="{self._esc(filters['keyword'])}" placeholder="kitchen tools distributor"></label>
                    <label><span>标签</span><input name="tag" value="{self._esc(filters['tag'])}" placeholder="重点客户, 私牌"></label>
                    <label><span>搜索</span><input name="search" value="{self._esc(filters['search'])}" placeholder="公司名 / 网站 / 类型"></label>
                    <button type="submit">应用筛选</button>
                </form>
            </article>
            <article class="panel full">
                <h2>客户列表</h2>
                <table>
                    <thead>
                        <tr><th>公司</th><th>国家</th><th>网站</th><th>客户类型</th><th>状态</th><th>标签</th><th>匹配度</th><th>操作</th></tr>
                    </thead>
                    <tbody>
                        {''.join(rows) if rows else '<tr><td colspan="8" class="empty">还没有客户线索，先导入一批试试看。</td></tr>'}
                    </tbody>
                </table>
            </article>
        </section>
        {self._page_close()}
        """
        self._send_html(content)

    def _render_customer_detail(self, customer_id: int) -> None:
        customer = self.ctx.repository.get_customer(customer_id)
        if not customer:
            self._not_found()
            return

        profile_json = json.dumps(customer.get("profile_json") or {}, ensure_ascii=False, indent=2)
        send_history = customer.get("send_history") or []
        send_history_html = "".join(
            f"<div class='compact-item'><strong>{self._esc(item.get('sent_at', '-'))}</strong><span>{self._esc(item.get('recipient_email', '-'))}</span><small>{'成功' if item.get('ok') else '失败'} / {self._esc(item.get('subject', '-'))}</small></div>"
            for item in reversed(send_history)
        )
        options = "".join(
            f'<option value="{self._esc(status)}"{" selected" if self._label(status) == self._label(customer.get("status")) else ""}>{self._esc(status)}</option>'
            for status in STATUS_OPTIONS
        )
        reply_options = "".join(
            f'<option value="{self._esc(status)}">{self._esc(status)}</option>'
            for status in REPLY_STATUS_OPTIONS
        )
        products = customer.get("main_products") or []
        product_tags = "".join(f'<span class="tag">{self._esc(item)}</span>' for item in products)
        candidate_email_text = ", ".join(customer.get("email_candidates") or []) or "-"
        tags_text = ", ".join(self._label(tag) for tag in (customer.get("customer_tags") or []))
        website_summary_cn = self._build_summary_cn(customer)
        email_followup_hint = self._email_followup_hint(customer)
        match_level = customer.get("match_level") or "-"
        match_score = customer.get("match_score")
        match_summary = customer.get("match_summary") or "-"
        match_reasons = customer.get("match_reasons") or []
        match_reason_html = "".join(
            f"<span class='tag'>{self._esc(reason)}</span>" for reason in match_reasons[:4]
        )
        crawl_snapshot = customer.get("crawl_snapshot") or {}
        crawl_rows = "".join(
            f"<tr><td>{self._esc(self._label(item.get('page_type', '-')))}</td><td>{self._esc(item.get('title', '-'))}</td><td>{self._render_link(item.get('url', ''))}</td><td>{self._esc(item.get('preview', '-'))}</td></tr>"
            for item in (crawl_snapshot.get("pages") or [])
        )
        activity_rows = "".join(
            f"<tr><td>{self._esc(item.get('at', '-'))}</td><td>{self._esc(self._label(item.get('action', '-')))}</td><td>{self._esc(self._label(item.get('detail', '-')))}</td></tr>"
            for item in reversed((customer.get("activity_log") or [])[-20:])
        )
        basis_cards = self._render_basis_cards(customer.get("email_basis") or [])
        review_note = customer.get("draft_review_note") or ""
        invalid_panel = self._invalid_delete_panel(customer_id, customer)

        content = f"""
        {self._page_open(customer.get('company_name', '客户多功能窗口'))}
        <section class="hero">
            <div>
                <a href="/customers">返回工作台</a>
                <h1>{self._esc(customer.get('company_name') or '-')}</h1>
                <p class="subtitle">{self._esc(customer.get('country') or '-')} / {self._esc(customer.get('website') or '无官网')}</p>
            </div>
            <div class="detail-actions">
                <form method="post" action="/customers/{customer_id}/analyze"><button type="submit">重新生成画像与草稿</button></form>
            </div>
        </section>
        <section class="detail-grid">
            <article class="panel">
                <h2>客户概览</h2>
                <p><strong>状态：</strong>{self._esc(self._label(customer.get('status') or '-'))}</p>
                <p><strong>Place ID：</strong>{self._esc(customer.get('place_id') or '-')}</p>
                <p><strong>电话：</strong>{self._esc(customer.get('phone') or '-')}</p>
                <p><strong>行业：</strong>{self._esc(self._label(customer.get('industry') or '-'))}</p>
                <p><strong>关键词：</strong>{self._esc(customer.get('search_keyword') or '-')}</p>
                <p><strong>匹配评分：</strong>{self._esc(str(match_score) if match_score not in (None, '') else '-')} / 100</p>
                <p><strong>匹配等级：</strong>{self._esc(match_level)}</p>
                <p><strong>匹配判断：</strong>{self._esc(match_summary)}</p>
                <div class="tags">{match_reason_html or '<span class="empty-inline">暂无匹配依据</span>'}</div>
                <p><strong>更新时间：</strong>{self._esc(customer.get('updated_at') or '-')}</p>
                <form method="post" action="/customers/{customer_id}/status" class="stack">
                    <label><span>修改状态</span><select name="status">{options}</select></label>
                    <button type="submit">保存状态</button>
                </form>
            </article>
            <article class="panel">
                <h2>客户标记</h2>
                <p><strong>当前标签：</strong>{self._esc(tags_text or '-')}</p>
                <form method="post" action="/customers/{customer_id}/tags" class="stack">
                    <label><span>标签</span><input name="tags_text" value="{self._esc(tags_text)}" placeholder="重点客户, 德国, 私牌"></label>
                    <button type="submit">保存标签</button>
                </form>
            </article>
            <article class="panel">
                <h2>官网分析结果</h2>
                <p>{self._esc(customer.get('website_summary') or '还没有生成官网摘要。')}</p>
                <p><strong>中文判断摘要：</strong>{self._esc(website_summary_cn)}</p>
                <div class="tags">{product_tags or '<span class="empty-inline">暂无产品提取</span>'}</div>
                <p><strong>来源页面：</strong>{self._esc(customer.get('source_url') or '-')}</p>
                <p><strong>引用片段：</strong>{self._esc(customer.get('source_snippet') or '-')}</p>
                <p><strong>置信度：</strong>{self._esc(str(customer.get('confidence_score') or '-'))}</p>
                <p><strong>邮箱候选：</strong>{self._esc(candidate_email_text)}</p>
                {f'<p><strong>邮箱提示：</strong>{self._esc(email_followup_hint)}</p>' if email_followup_hint else ''}
            </article>
            <article class="panel">
                <h2>人工补充特征</h2>
                <p><strong>当前补充：</strong>{self._esc(customer.get('manual_research_note') or '-')}</p>
                <form method="post" action="/customers/{customer_id}/manual-note" class="stack">
                    <label><span>人工补充说明</span><textarea name="manual_research_note">{self._esc(customer.get('manual_research_note') or '')}</textarea></label>
                    <button type="submit">保存人工特征</button>
                </form>
            </article>
            <article class="panel full">
                <h2>个性化依据</h2>
                {basis_cards}
            </article>
            <article class="panel">
                <h2>客户画像</h2>
                <pre>{self._esc(profile_json)}</pre>
            </article>
            <article class="panel">
                <h2>回复与状态回写</h2>
                <p><strong>当前回复状态：</strong>{self._esc(self._label(customer.get('reply_status') or '-'))}</p>
                <p><strong>最近回复时间：</strong>{self._esc(customer.get('last_reply_at') or '-')}</p>
                <p><strong>停止联系：</strong>{'是' if customer.get('do_not_contact') else '否'}</p>
                <form method="post" action="/customers/{customer_id}/reply" class="stack">
                    <label><span>回复结果</span><select name="reply_status"><option value="">请选择</option>{reply_options}</select></label>
                    <label><span>备注</span><textarea name="reply_note" placeholder="例如：客户说暂时没有采购计划 / 邮箱退信 / 自动回复假期中。"></textarea></label>
                    <button type="submit">保存回复结果</button>
                </form>
            </article>
            <article class="panel full">
                <h2>开发信草稿与发送</h2>
                <div class="detail-grid">
                    <article class="panel">
                        <p><strong>审核状态：</strong>{self._esc(self._label(customer.get('draft_review_status') or '待审核'))}</p>
                        <p><strong>通过时间：</strong>{self._esc(customer.get('approved_at') or '-')}</p>
                        <form method="post" action="/customers/{customer_id}/draft" class="stack">
                            <label><span>Subject</span><input name="subject" value="{self._esc(customer.get('email_subject') or '')}"></label>
                            <label><span>正文</span><textarea name="body">{self._esc(customer.get('email_body') or '还没有生成邮件草稿。')}</textarea></label>
                            <label><span>审核备注</span><textarea name="review_note">{self._esc(review_note)}</textarea></label>
                            <button type="submit">保存草稿修改</button>
                        </form>
                        <form method="post" action="/customers/{customer_id}/approve" class="stack">
                            <label><span>通过备注</span><input name="review_note" value="{self._esc(review_note)}"></label>
                            <button type="submit">人工审核通过</button>
                        </form>
                        <p><strong>AI 痕迹风险：</strong>{self._esc(customer.get('email_ai_tone_risk') or '-')}</p>
                        <form method="post" action="/customers/{customer_id}/approve-send" class="stack">
                            <label><span>审核备注</span><input name="review_note" value="{self._esc(review_note)}"></label>
                            <label><span>发送到</span><input name="recipient_email" value="{self._esc(customer.get('contact_email') or '')}" placeholder="name@example.com"></label>
                            <button type="submit">审核并正式发送</button>
                        </form>
                    </article>
                    <article class="panel">
                        <p><strong>发送规则：</strong>所有邮件都必须先人工审核。</p>
                        <p><strong>最近发送状态：</strong>{self._esc(self._label(customer.get('last_send_status') or '-'))}</p>
                        <p><strong>最近失败原因：</strong>{self._esc(self._label(customer.get('last_send_error') or '-'))}</p>
                        <form method="post" action="/customers/{customer_id}/contact-email" class="stack">
                            <label><span>收件人邮箱</span><input name="contact_email" value="{self._esc(customer.get('contact_email') or '')}" placeholder="name@example.com"></label>
                            <button type="submit">保存收件人</button>
                        </form>
                        {f'<p><strong>人工提醒：</strong>{self._esc(email_followup_hint)}</p>' if email_followup_hint else ''}
                        <form method="post" action="/customers/{customer_id}/send" class="stack">
                            <label><span>发送到</span><input name="recipient_email" value="{self._esc(customer.get('contact_email') or '')}" placeholder="name@example.com"></label>
                            <button type="submit">仅发送（需已审核）</button>
                        </form>
                    </article>
                </div>
            </article>
            <article class="panel full">
                <h2>爬取信息归档</h2>
                <p><strong>抓取状态：</strong>{'成功' if crawl_snapshot.get('success') else ('未完成' if crawl_snapshot else '-')}</p>
                <p><strong>抓取页数：</strong>{self._esc(crawl_snapshot.get('page_count', '-'))}</p>
                <p><strong>抓取错误：</strong>{self._esc(crawl_snapshot.get('error') or '-')}</p>
                <p><strong>抓取到的邮箱：</strong>{self._esc(', '.join(crawl_snapshot.get('email_candidates') or []) or '-')}</p>
                <table>
                    <thead><tr><th>页面类型</th><th>标题</th><th>链接</th><th>文本预览</th></tr></thead>
                    <tbody>{crawl_rows or '<tr><td colspan="4" class="empty">还没有保存抓取归档。</td></tr>'}</tbody>
                </table>
            </article>
            {invalid_panel}
            <article class="panel">
                <h2>人工备注</h2>
                <form method="post" action="/customers/{customer_id}/note" class="stack">
                    <textarea name="note" placeholder="记录人工判断、发送计划或补充信息">{self._esc(customer.get('note') or '')}</textarea>
                    <button type="submit">保存备注</button>
                </form>
            </article>
            <article class="panel">
                <h2>发送记录</h2>
                {send_history_html or '<p>还没有发送记录。</p>'}
            </article>
            <article class="panel full">
                <h2>操作日志</h2>
                <table>
                    <thead><tr><th>时间</th><th>动作</th><th>详情</th></tr></thead>
                    <tbody>{activity_rows or '<tr><td colspan="3" class="empty">还没有操作日志。</td></tr>'}</tbody>
                </table>
            </article>
        </section>
        {self._page_close()}
        """
        self._send_html(content)

    def _render_basis_cards(self, items: list[dict[str, Any]]) -> str:
        if not items:
            return "<p>当前还没有可用的个性化依据。</p>"
        category_labels = {
            "company_positioning": "公司定位",
            "product_range": "产品范围",
            "private_label": "私牌/定制合作",
            "brand_owner": "自有品牌",
            "brand_story": "品牌表达",
            "general": "一般依据",
        }
        type_labels = {"fact": "事实", "inference": "推断"}
        cards: list[str] = []
        for item in items:
            quote = self._clean_basis_text(item.get("quote", ""))
            cards.append(
                f"""
                <div class="panel">
                    <p><strong>依据类型：</strong>{self._esc(category_labels.get(str(item.get('category', '')), '一般依据'))} / {self._esc(type_labels.get(str(item.get('type', '')), '依据'))}</p>
                    <p><strong>中文说明：</strong>{self._esc(self._basis_explanation_cn(item))}</p>
                    <p><strong>来源页面：</strong>{self._render_link(str(item.get('page', '')))}</p>
                    <p><strong>原文片段：</strong>{self._esc(quote or '-')}</p>
                </div>
                """
            )
        return "".join(cards)

    def _invalid_delete_panel(self, customer_id: int, customer: dict[str, Any]) -> str:
        if self._label(customer.get("status")) != STATUS_INVALID:
            return ""
        return f"""
        <article class="panel full">
            <h2>无效公司人工复核</h2>
            <p><strong>当前网站：</strong>{self._render_link(customer.get('website', ''))}</p>
            <p><strong>说明：</strong>人工确认该客户无效后，可以手动从当前客户库中删除。</p>
            <form method="post" action="/customers/{customer_id}/delete" class="stack">
                <button type="submit">确认删除该无效客户</button>
            </form>
        </article>
        """

    def _basis_explanation_cn(self, item: dict[str, Any]) -> str:
        quote = self._clean_basis_text(item.get("quote", ""))
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
        if "kitchen equipment" in lowered or "kitchen tools" in lowered:
            points.append("官网内容显示其产品覆盖厨房设备或厨房工具。")
        if not points:
            points.append("这条依据来自客户官网公开内容，可作为开发信中的个性化切入点。")
        return " ".join(points)

    def _build_summary_cn(self, customer: dict[str, Any]) -> str:
        customer_type = str(self._label(customer.get("customer_type") or "")).strip().lower()
        products = [
            str(item).strip()
            for item in (customer.get("main_products") or [])
            if str(item).strip()
        ]
        text_parts = [
            self._clean_basis_text(customer.get("website_summary", "")),
            self._clean_basis_text(customer.get("source_snippet", "")),
            self._clean_basis_text(customer.get("manual_research_note", "")),
        ]
        profile = customer.get("profile_json") or {}
        for item in profile.get("evidence", []) or []:
            text_parts.append(self._clean_basis_text(item.get("quote", "")))
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

    def _email_followup_hint(self, customer: dict[str, Any]) -> str:
        contact_email = str(customer.get("contact_email") or "").strip()
        email_candidates = [str(item).strip() for item in (customer.get("email_candidates") or []) if str(item).strip()]
        extraction_status = str(customer.get("extraction_status") or "").strip().lower()
        has_analysis = bool(
            str(customer.get("website_summary") or "").strip()
            or str(customer.get("source_url") or "").strip()
            or customer.get("confidence_score") not in (None, "")
            or extraction_status == "success"
        )
        if contact_email or email_candidates or not has_analysis:
            return ""
        return "已完成官网分析，但暂未抓到公开邮箱。建议你到官网的 Contact、About、Impressum 或页脚位置人工确认后再填写收件人邮箱。"

    def _company_intro_cn(self, customer: dict[str, Any]) -> str:
        summary = self._build_summary_cn(customer)
        first = summary.split("。")[0].strip()
        return f"{first}。" if first else (customer.get("search_keyword") or "-")

    def _analyze_customer(self, customer_id: int) -> None:
        customer = self.ctx.repository.get_customer(customer_id)
        if not customer:
            return
        snapshot = self.ctx.fetcher.fetch(
            customer.get("website", ""),
            company_name=customer.get("company_name", ""),
            industry=customer.get("industry", ""),
        )
        parsed = self.ctx.parser.parse(snapshot, fallback_industry=customer.get("industry", ""))
        profile = self.ctx.profile_generator.generate(customer, parsed)
        draft = self.ctx.email_generator.generate(customer, profile)
        self.ctx.repository.save_analysis(
            customer_id,
            parsed,
            profile,
            draft,
            snapshot=snapshot,
            email_candidates=snapshot.email_candidates,
        )

    def _clean_basis_text(self, text: str) -> str:
        cleaned = str(text or "")
        replacements = {
            "â€™": "'",
            "â€“": "-",
            "â€œ": '"',
            "â€": '"',
            "â€¦": "...",
            "芒聙聶": "'",
            "芒聙聯": "-",
            "芒聙聹": '"',
            "芒聙聺": '"',
            "芒聙娄": "...",
        }
        for old, new in replacements.items():
            cleaned = cleaned.replace(old, new)
        return cleaned.strip()

    def _read_form_data(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8")
        return parse_qs(raw, keep_blank_values=True)

    def _extract_customer_id(self, path: str) -> int | None:
        parts = [part for part in path.split("/") if part]
        if len(parts) < 2:
            return None
        try:
            return int(parts[1])
        except ValueError:
            return None

    def _redirect(self, location: str, cookies: dict[str, str] | None = None) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        for key, value in (cookies or {}).items():
            cookie = SimpleCookie()
            cookie[key] = value
            cookie[key]["path"] = "/"
            cookie[key]["httponly"] = True
            cookie[key]["samesite"] = "Lax"
            if not value:
                cookie[key]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
            self.send_header("Set-Cookie", cookie.output(header="").strip())
        self.end_headers()

    def _send_html(self, content: str, status: int = 200) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _not_found(self) -> None:
        self._send_html(
            f"{self._page_open('Not Found')}<section class='panel'><h1>404</h1><p>Page not found.</p></section>{self._page_close()}",
            status=404,
        )

    def _render_admin_login(self, query: dict[str, list[str]]) -> None:
        notice = query.get("notice", [""])[0]
        notice_type = query.get("notice_type", ["info"])[0]
        next_path = query.get("next", ["/admin/settings/email"])[0] or "/admin/settings/email"
        notice_html = ""
        if notice:
            notice_class = "warning" if notice_type == "warning" else "success"
            notice_html = f"<section class='panel notice {notice_class}'><p>{self._esc(notice)}</p></section>"
        content = f"""
        {self._page_open("管理员登录")}
        {notice_html}
        <section class="panel" style="max-width:520px; margin:0 auto;">
            <p class="eyebrow">Admin Access</p>
            <h2>管理员登录</h2>
            <p class="subtitle">SMTP 配置和自动发送规则仅对管理员开放。</p>
            <form method="post" action="/admin/login" class="stack">
                <input type="hidden" name="next" value="{self._esc(next_path)}">
                <label><span>用户名</span><input name="username" value="{self._esc(self.ctx.settings.admin_username)}"></label>
                <label><span>密码</span><input name="password" type="password" placeholder="请输入管理员密码"></label>
                <button type="submit">进入管理员设置</button>
            </form>
        </section>
        {self._page_close()}
        """
        self._send_html(content)

    def _render_admin_email_settings(self, query: dict[str, list[str]]) -> None:
        smtp = self.ctx.sender.status_summary()
        saved = self.ctx.repository.get_smtp_settings()
        notice = query.get("notice", [""])[0]
        notice_type = query.get("notice_type", ["info"])[0]
        notice_html = ""
        if notice:
            notice_class = "warning" if notice_type == "warning" else "success"
            notice_html = f"<section class='panel notice {notice_class}'><p>{self._esc(notice)}</p></section>"
        security = str(saved.get("security") or smtp.get("security") or "starttls")
        use_tls_checked = "checked" if bool(saved.get("use_tls") if saved.get("host") else self.ctx.settings.smtp_use_tls) else ""
        auto_send_checked = "checked" if bool(smtp.get("auto_send_on_approval")) else ""
        password_hint = "已保存（不会回显）" if saved.get("password") else "留空表示当前未保存密码"
        content = f"""
        {self._page_open("管理员 SMTP 设置")}
        {notice_html}
        <section class="hero">
            <div>
                <p class="eyebrow">Admin Settings</p>
                <h1>SMTP 邮箱配置</h1>
                <p class="subtitle">这里的发信设置将用于网站内正式发送和审核后自动发送。普通访问者无法进入此页面。</p>
            </div>
            <form method="post" action="/admin/logout" class="inline-form">
                <button type="submit">退出管理员</button>
            </form>
        </section>
        <section class="detail-grid">
            <article class="panel">
                <h2>当前状态</h2>
                <p><strong>来源：</strong>{self._esc("网站后台" if smtp.get("source") == "website" else ".env 环境变量")}</p>
                <p><strong>已配置：</strong>{'是' if smtp.get('configured') else '否'}</p>
                <p><strong>服务器：</strong>{self._esc(str(smtp.get('host') or '-'))}:{self._esc(str(smtp.get('port') or '-'))}</p>
                <p><strong>安全模式：</strong>{self._esc(str(smtp.get('security') or '-'))}</p>
                <p><strong>发件邮箱：</strong>{self._esc(str(smtp.get('from_email') or '-'))}</p>
                <p><strong>自动发送：</strong>{'开启' if smtp.get('auto_send_on_approval') else '关闭'}</p>
            </article>
            <article class="panel">
                <h2>配置说明</h2>
                <p><strong>管理员结构：</strong>当前是单管理员单邮箱配置，适合你先部署到服务器上运营。</p>
                <p><strong>密码处理：</strong>密码保存后不会回显；如果不想修改密码，保存时留空即可。</p>
                <p><strong>建议：</strong>先保存，再点“测试连接”；测试成功后再打开自动发送。</p>
            </article>
            <article class="panel full">
                <h2>SMTP 设置</h2>
                <form method="post" action="/admin/settings/email" class="grid">
                    <input type="hidden" name="intent" value="save">
                    <label><span>SMTP Host</span><input name="host" value="{self._esc(str(saved.get('host') or self.ctx.settings.smtp_host or ''))}" placeholder="smtp.example.com"></label>
                    <label><span>Port</span><input name="port" type="number" value="{self._esc(str(saved.get('port') or self.ctx.settings.smtp_port or 587))}"></label>
                    <label><span>用户名</span><input name="user" value="{self._esc(str(saved.get('user') or self.ctx.settings.smtp_user or ''))}" placeholder="name@example.com"></label>
                    <label><span>密码</span><input name="password" type="password" placeholder="{self._esc(password_hint)}"></label>
                    <label><span>发件邮箱</span><input name="from_email" value="{self._esc(str(saved.get('from_email') or self.ctx.settings.smtp_from_email or ''))}" placeholder="sales@example.com"></label>
                    <label><span>发件人名称</span><input name="from_name" value="{self._esc(str(saved.get('from_name') or self.ctx.settings.smtp_from_name or ''))}" placeholder="Your Company"></label>
                    <label><span>安全模式</span>
                        <select name="security">
                            <option value="starttls"{' selected' if security == 'starttls' else ''}>STARTTLS</option>
                            <option value="ssl"{' selected' if security == 'ssl' else ''}>SSL</option>
                            <option value="none"{' selected' if security == 'none' else ''}>None</option>
                        </select>
                    </label>
                    <label><span>超时秒数</span><input name="timeout_seconds" type="number" value="{self._esc(str(saved.get('timeout_seconds') or self.ctx.settings.smtp_timeout_seconds or 20))}"></label>
                    <label><span>STARTTLS 兼容开关</span><input name="use_tls" type="checkbox" {use_tls_checked}></label>
                    <label><span>审核后自动发送</span><input name="auto_send_on_approval" type="checkbox" {auto_send_checked}></label>
                    <button type="submit">保存 SMTP 设置</button>
                </form>
                <form method="post" action="/admin/settings/email" class="stack" style="margin-top:14px;">
                    <input type="hidden" name="intent" value="test">
                    <label><span>测试说明</span><input value="使用当前已填写或已保存的 SMTP 配置进行连通性测试" readonly></label>
                    <label><span>SMTP Host</span><input name="host" value="{self._esc(str(saved.get('host') or self.ctx.settings.smtp_host or ''))}"></label>
                    <label><span>Port</span><input name="port" type="number" value="{self._esc(str(saved.get('port') or self.ctx.settings.smtp_port or 587))}"></label>
                    <label><span>用户名</span><input name="user" value="{self._esc(str(saved.get('user') or self.ctx.settings.smtp_user or ''))}"></label>
                    <label><span>密码</span><input name="password" type="password" placeholder="{self._esc(password_hint)}"></label>
                    <label><span>发件邮箱</span><input name="from_email" value="{self._esc(str(saved.get('from_email') or self.ctx.settings.smtp_from_email or ''))}"></label>
                    <label><span>发件人名称</span><input name="from_name" value="{self._esc(str(saved.get('from_name') or self.ctx.settings.smtp_from_name or ''))}"></label>
                    <label><span>安全模式</span>
                        <select name="security">
                            <option value="starttls"{' selected' if security == 'starttls' else ''}>STARTTLS</option>
                            <option value="ssl"{' selected' if security == 'ssl' else ''}>SSL</option>
                            <option value="none"{' selected' if security == 'none' else ''}>None</option>
                        </select>
                    </label>
                    <label><span>超时秒数</span><input name="timeout_seconds" type="number" value="{self._esc(str(saved.get('timeout_seconds') or self.ctx.settings.smtp_timeout_seconds or 20))}"></label>
                    <label><span>STARTTLS 兼容开关</span><input name="use_tls" type="checkbox" {use_tls_checked}></label>
                    <label><span>审核后自动发送</span><input name="auto_send_on_approval" type="checkbox" {auto_send_checked}></label>
                    <button type="submit">测试 SMTP 连接</button>
                </form>
            </article>
        </section>
        {self._page_close()}
        """
        self._send_html(content)

    def _render_setup(self, query: dict[str, list[str]]) -> None:
        status = self.ctx.setup_status()
        smtp = self.ctx.sender.status_summary()
        saved = self.ctx.repository.get_smtp_settings()
        notice = query.get("notice", [""])[0]
        notice_type = query.get("notice_type", ["info"])[0]
        notice_html = ""
        if notice:
            notice_class = "warning" if notice_type == "warning" else "success"
            notice_html = f"<section class='panel notice {notice_class}'><p>{self._esc(notice)}</p></section>"

        required_items: list[str] = []
        if not status["google_maps_ready"]:
            required_items.append("Google Maps API key")
        if not status["admin_ready"]:
            required_items.append("Admin password")

        recommended_items: list[str] = []
        if not status["company_ready"]:
            recommended_items.append("Company profile")
        if not status["smtp_ready"]:
            recommended_items.append("SMTP email settings")

        security = str(saved.get("security") or self.ctx.settings.smtp_security or "starttls")
        use_tls_checked = (
            "checked"
            if bool(saved.get("use_tls") if saved.get("host") else self.ctx.settings.smtp_use_tls)
            else ""
        )
        auto_send_checked = (
            "checked"
            if bool(
                saved.get("auto_send_on_approval")
                if saved.get("host")
                else self.ctx.settings.smtp_auto_send_on_approval
            )
            else ""
        )
        smtp_password_hint = "Keep current password" if saved.get("password") else "Leave blank if unused"
        content = f"""
        {self._page_open("First Run Setup")}
        {notice_html}
        <section class="hero">
            <div>
                <p class="eyebrow">First Run Setup</p>
                <h1>安装后的首次配置</h1>
                <p class="subtitle">第三方第一次打开程序时，可以直接在这里填写 key、管理员密码和 SMTP，不需要手动改 .env 文件。</p>
            </div>
        </section>
        <section class="stats">
            <article>
                <span>Google Maps</span>
                <strong>{'Ready' if status['google_maps_ready'] else 'Missing'}</strong>
            </article>
            <article>
                <span>Admin</span>
                <strong>{'Ready' if status['admin_ready'] else 'Missing'}</strong>
            </article>
            <article>
                <span>Company</span>
                <strong>{'Ready' if status['company_ready'] else 'Recommended'}</strong>
            </article>
            <article>
                <span>SMTP</span>
                <strong>{'Ready' if status['smtp_ready'] else 'Optional'}</strong>
            </article>
        </section>
        <section class="detail-grid">
            <article class="panel">
                <h2>Required before entering the workspace</h2>
                <div class="tags">
                    {''.join(f"<span class='tag'>{self._esc(item)}</span>" for item in required_items) or "<span class='tag'>Everything required is ready</span>"}
                </div>
                <p class="subtitle">当前只强制要求两项：Google Maps key 和一个非默认管理员密码。这样第三方安装后可以先完成最关键的初始化。</p>
            </article>
            <article class="panel">
                <h2>Recommended next</h2>
                <div class="tags">
                    {''.join(f"<span class='tag'>{self._esc(item)}</span>" for item in recommended_items) or "<span class='tag'>Everything recommended is ready</span>"}
                </div>
                <p class="subtitle">Company profile 会影响邮件草稿内容；SMTP 配置好后，就可以直接在系统里测试发信和自动发送。</p>
            </article>
            <article class="panel full">
                <h2>Setup Form</h2>
                <form method="post" action="/setup" class="stack">
                    <div class="grid">
                        <label><span>Google Maps API Key</span><input name="google_maps_api_key" value="{self._esc(self.ctx.settings.google_maps_api_key)}" placeholder="AIza..."></label>
                        <label><span>Use system proxy for Google</span><input name="google_maps_use_env_proxy" type="checkbox" {'checked' if self.ctx.settings.google_maps_use_env_proxy else ''}></label>
                        <label><span>Google proxy URL</span><input name="google_maps_proxy_url" value="{self._esc(self.ctx.settings.google_maps_proxy_url)}" placeholder="http://127.0.0.1:7890"></label>
                        <label><span>Admin username</span><input name="admin_username" value="{self._esc(self.ctx.settings.admin_username)}"></label>
                        <label><span>Admin password</span><input name="admin_password" type="password" placeholder="Set a new admin password"></label>
                        <label><span>Company name</span><input name="your_company_name" value="{self._esc(self.ctx.settings.your_company_name)}" placeholder="Your Company"></label>
                        <label><span>Company type</span><input name="your_company_type" value="{self._esc(self.ctx.settings.your_company_type)}" placeholder="professional supplier"></label>
                        <label><span>Main products</span><input name="your_products" value="{self._esc(self.ctx.settings.your_products)}" placeholder="food-grade silicone kitchen tools"></label>
                        <label><span>Your advantage</span><input name="your_advantage" value="{self._esc(self.ctx.settings.your_advantage)}" placeholder="stable quality, reliable lead times"></label>
                        <label><span>MiniMax API Key</span><input name="minimax_api_key" value="{self._esc(self.ctx.settings.minimax_api_key)}" placeholder="Optional"></label>
                        <label><span>MiniMax Base URL</span><input name="minimax_base_url" value="{self._esc(self.ctx.settings.minimax_base_url)}" placeholder="Optional"></label>
                        <label><span>MiniMax Model</span><input name="minimax_model" value="{self._esc(self.ctx.settings.minimax_model)}" placeholder="Optional"></label>
                    </div>
                    <div class="panel" style="margin:0;">
                        <h3 style="margin-top:0;">SMTP (optional but recommended)</h3>
                        <div class="grid">
                            <label><span>SMTP Host</span><input name="host" value="{self._esc(str(saved.get('host') or self.ctx.settings.smtp_host or ''))}" placeholder="smtp.example.com"></label>
                            <label><span>Port</span><input name="port" type="number" value="{self._esc(str(saved.get('port') or self.ctx.settings.smtp_port or 587))}"></label>
                            <label><span>SMTP User</span><input name="user" value="{self._esc(str(saved.get('user') or self.ctx.settings.smtp_user or ''))}" placeholder="name@example.com"></label>
                            <label><span>SMTP Password</span><input name="password" type="password" placeholder="{self._esc(smtp_password_hint)}"></label>
                            <label><span>From email</span><input name="from_email" value="{self._esc(str(saved.get('from_email') or self.ctx.settings.smtp_from_email or ''))}" placeholder="sales@example.com"></label>
                            <label><span>From name</span><input name="from_name" value="{self._esc(str(saved.get('from_name') or self.ctx.settings.smtp_from_name or ''))}" placeholder="Your Company"></label>
                            <label><span>Security</span>
                                <select name="security">
                                    <option value="starttls"{' selected' if security == 'starttls' else ''}>STARTTLS</option>
                                    <option value="ssl"{' selected' if security == 'ssl' else ''}>SSL</option>
                                    <option value="none"{' selected' if security == 'none' else ''}>None</option>
                                </select>
                            </label>
                            <label><span>Timeout seconds</span><input name="timeout_seconds" type="number" value="{self._esc(str(saved.get('timeout_seconds') or self.ctx.settings.smtp_timeout_seconds or 20))}"></label>
                            <label><span>Enable STARTTLS fallback</span><input name="use_tls" type="checkbox" {use_tls_checked}></label>
                            <label><span>Auto send after approval</span><input name="auto_send_on_approval" type="checkbox" {auto_send_checked}></label>
                        </div>
                    </div>
                    <div class="grid">
                        <button type="submit" name="intent" value="save">Save setup and enter workspace</button>
                        <button type="submit" name="intent" value="save_and_test">Save setup and test SMTP</button>
                    </div>
                </form>
            </article>
        </section>
        {self._page_close()}
        """
        self._send_html(content)

    def _handle_setup_submit(self, data: dict[str, list[str]]) -> None:
        intent = data.get("intent", ["save"])[0] or "save"
        smtp_payload = self._smtp_payload_from_form(data)
        admin_password = data.get("admin_password", [""])[0].strip() or self.ctx.settings.admin_password
        env_updates = {
            "GOOGLE_MAPS_API_KEY": data.get("google_maps_api_key", [""])[0].strip(),
            "GOOGLE_MAPS_USE_ENV_PROXY": data.get("google_maps_use_env_proxy", [""])[0] == "on",
            "GOOGLE_MAPS_PROXY_URL": data.get("google_maps_proxy_url", [""])[0].strip(),
            "MINIMAX_API_KEY": data.get("minimax_api_key", [""])[0].strip(),
            "MINIMAX_BASE_URL": data.get("minimax_base_url", [""])[0].strip(),
            "MINIMAX_MODEL": data.get("minimax_model", [""])[0].strip(),
            "YOUR_COMPANY_NAME": data.get("your_company_name", [""])[0].strip(),
            "YOUR_COMPANY_TYPE": data.get("your_company_type", [""])[0].strip(),
            "YOUR_PRODUCTS": data.get("your_products", [""])[0].strip(),
            "YOUR_ADVANTAGE": data.get("your_advantage", [""])[0].strip(),
            "EMAIL_HOST": smtp_payload["host"],
            "EMAIL_PORT": smtp_payload["port"],
            "EMAIL_USER": smtp_payload["user"],
            "EMAIL_PASSWORD": smtp_payload["password"],
            "EMAIL_FROM": smtp_payload["from_email"],
            "EMAIL_FROM_NAME": smtp_payload["from_name"],
            "EMAIL_SECURITY": smtp_payload["security"],
            "EMAIL_USE_TLS": smtp_payload["use_tls"],
            "EMAIL_TIMEOUT_SECONDS": smtp_payload["timeout_seconds"],
            "EMAIL_AUTO_SEND_ON_APPROVAL": smtp_payload["auto_send_on_approval"],
            "ADMIN_USERNAME": data.get("admin_username", [""])[0].strip() or self.ctx.settings.admin_username,
            "ADMIN_PASSWORD": admin_password,
        }
        save_runtime_env(env_updates)
        self.ctx.repository.save_smtp_settings(**smtp_payload)
        self.ctx.refresh_runtime_configuration()

        if intent == "save_and_test":
            if not smtp_payload["host"] or not smtp_payload["from_email"]:
                self._redirect(
                    "/setup?"
                    + urlencode(
                        {
                            "notice": "Setup saved, but SMTP is still incomplete. Fill host and from email before testing.",
                            "notice_type": "warning",
                        }
                    )
                )
                return
            try:
                self.ctx.sender.test_connection()
            except Exception as exc:
                self._redirect(
                    "/setup?"
                    + urlencode(
                        {
                            "notice": f"Setup saved, but SMTP test failed: {type(exc).__name__}: {exc}",
                            "notice_type": "warning",
                        }
                    )
                )
                return

        status = self.ctx.setup_status()
        missing_items: list[str] = []
        if not status["google_maps_ready"]:
            missing_items.append("Google Maps API key")
        if not status["admin_ready"]:
            missing_items.append("Admin password")

        if missing_items:
            self._redirect(
                "/setup?"
                + urlencode(
                    {
                        "notice": "Setup saved, but these required fields are still incomplete: "
                        + ", ".join(missing_items),
                        "notice_type": "warning",
                    }
                )
            )
            return

        success_notice = "Setup saved successfully."
        if intent == "save_and_test":
            success_notice = "Setup saved successfully and SMTP test passed."
        self._redirect(
            "/?"
            + urlencode(
                {
                    "notice": success_notice,
                    "notice_type": "success",
                }
            )
        )

    def _cookie_value(self, name: str) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(name)
        return morsel.value if morsel else ""

    def _is_admin_authenticated(self) -> bool:
        return self.ctx.has_admin_session(self._cookie_value("admin_session"))

    def _require_admin(self, next_path: str) -> bool:
        if self._is_admin_authenticated():
            return True
        self._redirect("/admin/login?" + urlencode({"next": next_path}))
        return False

    def _smtp_payload_from_form(self, data: dict[str, list[str]]) -> dict[str, Any]:
        current = self.ctx.repository.get_smtp_settings()
        port_raw = data.get("port", [""])[0].strip() or str(
            current.get("port") or self.ctx.settings.smtp_port or "587"
        )
        timeout_raw = data.get("timeout_seconds", [""])[0].strip() or str(
            current.get("timeout_seconds") or self.ctx.settings.smtp_timeout_seconds or "20"
        )
        password_raw = data.get("password", [""])[0].strip()
        return {
            "host": data.get("host", [""])[0],
            "port": int(port_raw or 587),
            "user": data.get("user", [""])[0],
            "password": password_raw or str(current.get("password") or self.ctx.settings.smtp_password or ""),
            "from_email": data.get("from_email", [""])[0],
            "from_name": data.get("from_name", [""])[0],
            "security": data.get("security", ["starttls"])[0] or "starttls",
            "use_tls": (data.get("use_tls", [""])[0] == "on"),
            "timeout_seconds": int(timeout_raw or 20),
            "auto_send_on_approval": (data.get("auto_send_on_approval", [""])[0] == "on"),
        }

    def _page_open(self, title: str) -> str:
        return f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{self._esc(title)}</title>
            <style>
                :root {{
                    --paper:#ffffff; --paper-soft:#f8fafc; --ink:#1f2937; --muted:#6b7280;
                    --line:#e5e7eb; --accent:#0f9aaa; --accent-strong:#0b7285; --accent-soft:#e1f6f8;
                    --sidebar:#f3f6fa; --shadow:0 20px 45px rgba(15,23,42,0.08);
                }}
                * {{ box-sizing:border-box; }}
                body {{
                    margin:0; font-family:Segoe UI,Arial,sans-serif; color:var(--ink);
                    background:linear-gradient(180deg,#edf2f7 0%,#f7f9fc 100%);
                }}
                .app-shell {{ min-height:100vh; display:grid; grid-template-columns:240px minmax(0,1fr); }}
                .sidebar {{ background:var(--sidebar); border-right:1px solid var(--line); padding:26px 18px; display:flex; flex-direction:column; gap:22px; }}
                .brand {{ display:flex; gap:12px; align-items:center; }}
                .badge {{ width:40px; height:40px; border-radius:14px; display:grid; place-items:center; background:var(--accent-soft); color:var(--accent-strong); font-weight:700; }}
                .brand strong {{ display:block; }}
                .brand small {{ color:var(--muted); }}
                .nav {{ display:grid; gap:8px; }}
                .nav a {{ text-decoration:none; padding:11px 13px; border-radius:14px; color:var(--muted); font-weight:600; }}
                .nav a:hover {{ background:#fff; color:var(--ink); box-shadow:0 8px 20px rgba(15,23,42,0.06); }}
                .note-title {{ margin:0 0 10px; font-size:13px; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:0.08em; }}
                .note-list {{ margin:0; padding-left:18px; display:grid; gap:8px; color:var(--muted); font-size:14px; }}
                .workspace {{ padding:24px 28px 36px; }}
                .hero {{ display:flex; justify-content:space-between; gap:16px; margin-bottom:20px; align-items:flex-start; }}
                .eyebrow {{ text-transform:uppercase; letter-spacing:0.18em; color:var(--accent-strong); font-size:12px; margin:0 0 8px; font-weight:700; }}
                .subtitle, small, .empty, .empty-inline {{ color:var(--muted); }}
                .panel {{ background:var(--paper); border:1px solid var(--line); border-radius:22px; padding:20px; box-shadow:var(--shadow); margin-bottom:18px; }}
                .notice.success {{ border-color:#b7ebc6; background:#effcf3; }}
                .notice.warning {{ border-color:#facc15; background:#fff8db; }}
                .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; align-items:end; }}
                .stack {{ display:grid; gap:12px; }}
                .stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; margin-bottom:18px; }}
                .stats article {{ background:var(--paper-soft); border:1px solid var(--line); border-radius:18px; padding:16px; box-shadow:var(--shadow); }}
                .stats span {{ display:block; color:var(--muted); margin-bottom:8px; }}
                .stats strong {{ font-size:30px; }}
                input, select, textarea, button {{ font:inherit; }}
                input, select, textarea {{ width:100%; border:1px solid var(--line); border-radius:14px; padding:12px; background:#fff; }}
                label span {{ display:block; margin-bottom:6px; color:var(--muted); font-size:13px; font-weight:700; }}
                textarea {{ min-height:220px; resize:vertical; }}
                button {{ border:none; border-radius:14px; padding:12px 18px; background:var(--accent); color:#fff; cursor:pointer; font-weight:700; }}
                table {{ width:100%; border-collapse:collapse; }}
                th, td {{ text-align:left; padding:12px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
                th {{ color:var(--muted); font-size:13px; text-transform:uppercase; letter-spacing:0.08em; }}
                .pill, .tag {{ display:inline-flex; padding:6px 10px; border-radius:999px; background:var(--accent-soft); color:var(--accent-strong); font-size:13px; font-weight:600; margin:4px 6px 0 0; }}
                .detail-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; }}
                .full {{ grid-column:1 / -1; }}
                .tags {{ margin-top:12px; }}
                pre {{ overflow-x:auto; white-space:pre-wrap; background:var(--paper-soft); border-radius:14px; padding:14px; }}
                .compact-list {{ display:grid; gap:12px; }}
                .compact-item {{ background:var(--paper-soft); border:1px solid var(--line); border-radius:16px; padding:14px; }}
                .compact-item strong, .compact-item span, .compact-item small {{ display:block; }}
                .inline-form {{ display:inline; margin-left:10px; }}
                .link-button {{
                    background:none; border:none; padding:0; margin:0; cursor:pointer;
                    color:var(--accent-strong); font-weight:700;
                }}
                .danger-text {{ color:#b42318; }}
                .anchor-target {{ position:relative; top:-10px; }}
                a {{ color:inherit; }}
                @media (max-width: 980px) {{ .app-shell {{ grid-template-columns:1fr; }} .sidebar {{ border-right:none; border-bottom:1px solid var(--line); }} }}
                @media (max-width: 860px) {{ .detail-grid {{ grid-template-columns:1fr; }} .hero {{ flex-direction:column; }} .workspace {{ padding:18px; }} }}
            </style>
        </head>
        <body><div class="app-shell"><aside class="sidebar">
            <div class="brand">
                <span class="badge">AI</span>
                <div>
                    <strong>{self._esc(self.ctx.settings.app_name)}</strong>
                    <small>客户开发辅助工作台</small>
                </div>
            </div>
            <nav class="nav">
                <a href="/setup">First-run setup</a>
                <a href="/customers">工作台</a>
                <a href="/customers#new-search">搜索新客户</a>
                <a href="/customers?status={quote_plus(STATUS_SENT)}">已发送</a>
                <a href="/customers?status={quote_plus(STATUS_REVIEW)}">待人工审核</a>
                <a href="/customers?tag={quote_plus('重点客户')}">重点客户</a>
                <a href="/admin/settings/email">管理员设置</a>
            </nav>
            <div>
                <p class="note-title">当前原则</p>
                <ul class="note-list">
                    <li>邮件必须先人工审核</li>
                    <li>官网证据优先</li>
                    <li>客户标记与日志留痕</li>
                </ul>
            </div>
        </aside><main class="workspace">
        """

    def _page_close(self) -> str:
        return """
        <script>
        document.addEventListener("DOMContentLoaded", function () {
            const tables = document.querySelectorAll("table");
            tables.forEach(function (table) {
                const headerText = table.querySelector("thead")?.textContent || "";
                if (!headerText.includes("操作") || !headerText.includes("公司")) {
                    return;
                }
                const rows = table.querySelectorAll("tbody tr");
                rows.forEach(function (row) {
                    const actionCell = row.querySelector("td:last-child");
                    if (!actionCell) {
                        return;
                    }
                    const detailLink = actionCell.querySelector('a[href^="/customers/"]');
                    if (!detailLink) {
                        return;
                    }
                    const path = detailLink.getAttribute("href") || "";
                    if (!path || actionCell.querySelector('form[action$="/delete"]')) {
                        return;
                    }

                    const deleteForm = document.createElement("form");
                    deleteForm.method = "post";
                    deleteForm.action = path + "/delete";
                    deleteForm.className = "inline-form";
                    deleteForm.onsubmit = function () {
                        return window.confirm("确认删除这个客户吗？");
                    };

                    const deleteButton = document.createElement("button");
                    deleteButton.type = "submit";
                    deleteButton.className = "link-button danger-text";
                    deleteButton.textContent = "删除";

                    deleteForm.appendChild(deleteButton);
                    actionCell.appendChild(deleteForm);
                });
            });
        });
        </script>
        </main></div></body></html>
        """

    def _render_link(self, website: str) -> str:
        if not website:
            return '<span class="empty-inline">无官网</span>'
        safe = self._esc(website)
        return f'<a href="{safe}" target="_blank" rel="noreferrer">{safe}</a>'

    def _esc(self, value: Any) -> str:
        return html.escape(str(value), quote=True)

    def _label(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        return ACTION_ALIASES.get(STATUS_ALIASES.get(text, text), STATUS_ALIASES.get(text, text))

    def log_message(self, format: str, *args: object) -> None:
        return


def run_simple_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    settings: Settings | None = None,
) -> None:
    context = SimpleAppContext(settings or get_settings())
    server = ThreadingHTTPServer((host, port), SimpleMVPHandler)
    server.context = context  # type: ignore[attr-defined]
    print(f"Running fallback MVP server at http://{host}:{port}")
    server.serve_forever()
