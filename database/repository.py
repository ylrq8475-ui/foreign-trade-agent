from __future__ import annotations

import json
import sqlite3
import hashlib
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from config.factory_profile import default_factory_knowledge
from config.statuses import (
    DRAFT_STATUS_APPROVED,
    DRAFT_STATUS_PENDING,
    REPLY_STATUS_AUTO_REPLY,
    REPLY_STATUS_BOUNCED,
    REPLY_STATUS_REJECTED,
    REPLY_STATUS_REPLIED,
    STATUS_DRAFTED,
    STATUS_FOLLOWING,
    STATUS_INVALID,
    STATUS_NEW,
    STATUS_REPLIED,
    STATUS_REVIEW,
    STATUS_SENT,
)
from database.models import (
    CustomerProfileResult,
    EmailDraftResult,
    Lead,
    ParsedWebsite,
    WebsiteSnapshot,
)


class CustomerRepository:
    def __init__(
        self,
        db_path: Path,
        *,
        journal_mode: str = "memory",
        synchronous: str = "off",
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.journal_mode = (journal_mode or "memory").strip().lower()
        self.synchronous = (synchronous or "off").strip().lower()

    def init_db(self) -> None:
        try:
            self._ensure_schema()
        except sqlite3.Error:
            self._reset_broken_db_file()
            self._ensure_schema()
        self._migrate_legacy_json_if_needed()
        self.ensure_factory_knowledge_seeded()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    place_id TEXT NOT NULL,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    company_name TEXT NOT NULL,
                    country TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_place_id
                ON customers(place_id)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS saved_searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_prefix TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    token_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    scopes TEXT NOT NULL,
                    note TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_used_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_usage_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_id INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    method TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    request_summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(token_id) REFERENCES api_tokens(id)
                )
                """
            )
            conn.commit()

    def upsert_lead(self, lead: Lead) -> int:
        now = self._now()
        dedupe_key = f"{lead.company_name.lower().strip()}::{lead.country.lower().strip()}"
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, payload FROM customers
                WHERE place_id = ? OR dedupe_key = ?
                LIMIT 1
                """,
                (lead.place_id, dedupe_key),
            ).fetchone()
            if row:
                customer = self._decode_payload(row["payload"])
                customer.update(
                    {
                        "company_name": lead.company_name,
                        "country": lead.country,
                        "city": lead.city,
                        "address": lead.address,
                        "website": lead.website,
                        "phone": lead.phone,
                        "industry": lead.industry,
                        "search_keyword": lead.search_keyword,
                        "source_platform": lead.source_platform,
                        "dedupe_key": dedupe_key,
                        "updated_at": now,
                    }
                )
                self._append_log(customer, "线索更新", f"刷新了 {lead.company_name} 的基础信息。")
                self._save_customer_payload(conn, int(row["id"]), customer)
                return int(row["id"])

            customer = self._new_customer_payload(lead, dedupe_key=dedupe_key, now=now)
            self._append_log(
                customer,
                "线索导入",
                f"通过 {lead.source_platform} 导入客户线索，关键词：{lead.search_keyword or '-'}。",
            )
            customer_id = self._insert_customer_payload(conn, customer)
            return customer_id

    def list_customers(
        self,
        *,
        status: str = "",
        country: str = "",
        keyword: str = "",
        search: str = "",
        tag: str = "",
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM customers
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        customers = [self._normalize(self._decode_payload(row["payload"])) for row in rows]
        status = status.strip()
        country = country.strip().lower()
        keyword = keyword.strip().lower()
        search = search.strip().lower()
        tag = tag.strip().lower()

        def matches(customer_row: dict[str, Any]) -> bool:
            if status and customer_row.get("status") != status:
                return False
            if country and country not in str(customer_row.get("country", "")).lower():
                return False
            if keyword and keyword not in str(customer_row.get("search_keyword", "")).lower():
                return False
            if tag and not any(tag in item.lower() for item in customer_row.get("customer_tags", [])):
                return False
            if search:
                haystack = " ".join(
                    [
                        str(customer_row.get("company_name", "")),
                        str(customer_row.get("website", "")),
                        str(customer_row.get("customer_type", "")),
                        str(customer_row.get("industry", "")),
                        str(customer_row.get("manual_research_note", "")),
                        " ".join(customer_row.get("customer_tags", [])),
                    ]
                ).lower()
                if search not in haystack:
                    return False
            return True

        return [customer_row for customer_row in customers if matches(customer_row)]

    def get_customer(self, customer_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM customers WHERE id = ?",
                (int(customer_id),),
            ).fetchone()
        if not row:
            return None
        return self._normalize(self._decode_payload(row["payload"]))

    def list_saved_searches(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM saved_searches
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._decode_payload(row["payload"]) for row in rows]

    def save_saved_search(
        self,
        *,
        query: str,
        country: str,
        limit: int,
        search_mode: str = "balanced",
        note: str = "",
    ) -> int:
        now = self._now()
        query = query.strip()
        country = country.strip()
        search_mode = (search_mode or "balanced").strip()
        note = note.strip()
        dedupe_key = f"{query.lower()}::{country.lower()}::{search_mode.lower()}"
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, payload FROM saved_searches WHERE dedupe_key = ?",
                (dedupe_key,),
            ).fetchone()
            payload = {
                "query": query,
                "country": country,
                "limit": int(limit),
                "search_mode": search_mode,
                "note": note,
                "dedupe_key": dedupe_key,
                "updated_at": now,
            }
            if row:
                current = self._decode_payload(row["payload"])
                current.update(payload)
                conn.execute(
                    """
                    UPDATE saved_searches
                    SET updated_at = ?, payload = ?
                    WHERE id = ?
                    """,
                    (now, self._encode_payload(current), int(row["id"])),
                )
                conn.commit()
                return int(row["id"])

            payload["created_at"] = now
            cursor = conn.execute(
                """
                INSERT INTO saved_searches(dedupe_key, updated_at, payload)
                VALUES (?, ?, ?)
                """,
                (dedupe_key, now, self._encode_payload(payload)),
            )
            saved_id = int(cursor.lastrowid)
            payload["id"] = saved_id
            conn.execute(
                "UPDATE saved_searches SET payload = ? WHERE id = ?",
                (self._encode_payload(payload), saved_id),
            )
            conn.commit()
            return saved_id

    def delete_saved_search(self, saved_search_id: int) -> None:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM saved_searches WHERE id = ?",
                (int(saved_search_id),),
            )
            conn.commit()
        if cursor.rowcount == 0:
            raise ValueError(f"Saved search {saved_search_id} not found")

    def ensure_factory_knowledge_seeded(self) -> None:
        existing = self._get_app_setting_payload("factory_knowledge")
        if existing:
            return
        knowledge = default_factory_knowledge()
        knowledge["updated_at"] = self._now()
        self._save_app_setting_payload("factory_knowledge", knowledge)

    def get_factory_knowledge(self) -> dict[str, Any]:
        current = self._get_app_setting_payload("factory_knowledge")
        if not current:
            seeded = default_factory_knowledge()
            seeded["updated_at"] = self._now()
            self._save_app_setting_payload("factory_knowledge", seeded)
            return seeded
        base = default_factory_knowledge()
        return self._deep_merge(base, current)

    def save_factory_knowledge(self, knowledge: dict[str, Any]) -> dict[str, Any]:
        merged = self._deep_merge(default_factory_knowledge(), dict(knowledge or {}))
        merged["updated_at"] = self._now()
        self._save_app_setting_payload("factory_knowledge", merged)
        return merged

    def get_smtp_settings(self) -> dict[str, Any]:
        smtp = self._get_app_setting_payload("smtp")
        smtp.setdefault("host", "")
        smtp.setdefault("port", "")
        smtp.setdefault("user", "")
        smtp.setdefault("password", "")
        smtp.setdefault("from_email", "")
        smtp.setdefault("from_name", "")
        smtp.setdefault("security", "")
        smtp.setdefault("use_tls", True)
        smtp.setdefault("timeout_seconds", "")
        smtp.setdefault("auto_send_on_approval", False)
        smtp.setdefault("updated_at", "")
        return smtp

    def save_smtp_settings(
        self,
        *,
        host: str,
        port: int | str,
        user: str,
        password: str,
        from_email: str,
        from_name: str,
        security: str,
        use_tls: bool,
        timeout_seconds: int | str,
        auto_send_on_approval: bool,
    ) -> None:
        current = self.get_smtp_settings()
        password_value = password.strip() if str(password).strip() else str(current.get("password", ""))
        smtp = {
            "host": host.strip(),
            "port": int(str(port).strip() or 0),
            "user": user.strip(),
            "password": password_value,
            "from_email": from_email.strip(),
            "from_name": from_name.strip(),
            "security": security.strip().lower(),
            "use_tls": bool(use_tls),
            "timeout_seconds": int(str(timeout_seconds).strip() or 20),
            "auto_send_on_approval": bool(auto_send_on_approval),
            "updated_at": self._now(),
        }
        self._save_app_setting_payload("smtp", smtp)

    def create_api_token(
        self,
        *,
        token_name: str,
        scopes: list[str] | None = None,
        note: str = "",
        expires_at: str = "",
    ) -> dict[str, Any]:
        now = self._now()
        raw_token = f"cwa_{secrets.token_urlsafe(24)}"
        token_hash = self._hash_token(raw_token)
        token_prefix = raw_token[:12]
        scopes = list(dict.fromkeys([item.strip() for item in (scopes or []) if item.strip()]))
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO api_tokens(
                    token_prefix, token_hash, token_name, status, scopes, note,
                    created_at, updated_at, expires_at, last_used_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token_prefix,
                    token_hash,
                    token_name.strip(),
                    "active",
                    json.dumps(scopes, ensure_ascii=False),
                    note.strip(),
                    now,
                    now,
                    expires_at.strip(),
                    "",
                ),
            )
            token_id = int(cursor.lastrowid)
            conn.commit()
        token_meta = self.get_api_token(token_id) or {}
        token_meta["plain_token"] = raw_token
        return token_meta

    def list_api_tokens(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM api_tokens
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._normalize_api_token_row(row) for row in rows]

    def get_api_token(self, token_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM api_tokens WHERE id = ?",
                (int(token_id),),
            ).fetchone()
        if not row:
            return None
        return self._normalize_api_token_row(row)

    def revoke_api_token(self, token_id: int) -> None:
        now = self._now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE api_tokens
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                ("revoked", now, int(token_id)),
            )
            conn.commit()
        if cursor.rowcount == 0:
            raise ValueError(f"API token {token_id} not found")

    def authenticate_api_token(self, raw_token: str) -> dict[str, Any] | None:
        token = str(raw_token or "").strip()
        if not token:
            return None
        token_hash = self._hash_token(token)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM api_tokens WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if not row:
                return None
            token_row = self._normalize_api_token_row(row)
            if token_row.get("status") != "active":
                return None
            expires_at = str(token_row.get("expires_at") or "").strip()
            if expires_at and expires_at < self._now():
                return None
            conn.execute(
                """
                UPDATE api_tokens
                SET last_used_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (self._now(), self._now(), int(token_row["id"])),
            )
            conn.commit()
        token_row["last_used_at"] = self._now()
        return token_row

    def record_api_usage(
        self,
        *,
        token_id: int,
        path: str,
        method: str,
        status_code: int,
        request_summary: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO api_usage_logs(
                    token_id, path, method, status_code, request_summary, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(token_id),
                    path.strip(),
                    method.strip().upper(),
                    int(status_code),
                    request_summary.strip(),
                    self._now(),
                ),
            )
            conn.commit()

    def save_analysis(
        self,
        customer_id: int,
        parsed: ParsedWebsite,
        profile: CustomerProfileResult,
        draft: EmailDraftResult,
        *,
        snapshot: WebsiteSnapshot | None = None,
        email_candidates: list[str] | None = None,
    ) -> None:
        current = self.get_customer(customer_id) or {}
        current_email = current.get("contact_email", "")
        candidates = list(dict.fromkeys(email_candidates or current.get("email_candidates", []) or []))
        if not current_email and candidates:
            current_email = candidates[0]
        preserve_existing_draft = self._should_preserve_existing_draft(
            current=current,
            parsed=parsed,
            draft=draft,
        )
        updates = {
            "status": STATUS_REVIEW,
            "website_summary": parsed.website_summary,
            "main_products": profile.main_products,
            "customer_type": profile.customer_type,
            "personalization_points": parsed.personalization_points,
            "source_url": parsed.source_url,
            "source_snippet": parsed.source_snippet,
            "confidence_score": profile.confidence_score,
            "review_required": profile.review_required or draft.review_required,
            "extraction_status": parsed.extraction_status,
            "profile_json": profile.to_dict(),
            "email_candidates": candidates,
            "contact_email": current_email,
        }
        if preserve_existing_draft:
            updates.update(
                {
                    "status": current.get("status", STATUS_REVIEW),
                    "email_subject": current.get("email_subject", ""),
                    "email_body": current.get("email_body", ""),
                    "email_basis": current.get("email_basis", []),
                    "email_ai_tone_risk": current.get("email_ai_tone_risk", ""),
                    "draft_review_status": current.get("draft_review_status", DRAFT_STATUS_PENDING),
                    "draft_review_note": current.get("draft_review_note", ""),
                    "approved_at": current.get("approved_at", ""),
                    "last_send_status": current.get("last_send_status", ""),
                    "last_send_error": current.get("last_send_error", ""),
                }
            )
        else:
            updates.update(
                {
                    "email_subject": draft.subject,
                    "email_body": draft.body,
                    "email_basis": draft.personalization_basis,
                    "email_ai_tone_risk": draft.ai_tone_risk,
                    "draft_review_status": DRAFT_STATUS_PENDING,
                    "draft_review_note": "",
                    "approved_at": "",
                    "last_send_status": "",
                    "last_send_error": "",
                }
            )
        if snapshot:
            updates["crawl_snapshot"] = self._serialize_snapshot(snapshot)
        self._update_customer(customer_id, updates)
        detail = f"完成官网抓取、画像分析和草稿生成，抽取状态：{parsed.extraction_status}。"
        if preserve_existing_draft:
            detail += " 本次抓取质量不足，已保留原有草稿与审核状态。"
        self._log_customer_action(
            customer_id,
            "分析完成",
            detail,
        )

    def _should_preserve_existing_draft(
        self,
        *,
        current: dict[str, Any],
        parsed: ParsedWebsite,
        draft: EmailDraftResult,
    ) -> bool:
        if not self._draft_has_meaningful_content(current):
            return False
        if parsed.extraction_status != "success":
            return True
        if not draft.personalization_basis:
            return True
        return self._draft_is_placeholder(subject=draft.subject, body=draft.body)

    def _draft_has_meaningful_content(self, payload: dict[str, Any]) -> bool:
        subject = str(payload.get("email_subject", "") or "").strip()
        body = str(payload.get("email_body", "") or "").strip()
        if not subject or not body:
            return False
        if self._draft_is_placeholder(subject=subject, body=body):
            return False
        if payload.get("email_basis"):
            return True
        return payload.get("draft_review_status") == DRAFT_STATUS_APPROVED

    def _draft_is_placeholder(self, *, subject: str, body: str) -> bool:
        normalized_subject = subject.strip().lower()
        normalized_body = body.strip().lower()
        return (
            "information insufficient" in normalized_subject
            or "please review the website content manually" in normalized_body
        )

    def update_status(self, customer_id: int, status: str) -> None:
        self._update_customer(customer_id, {"status": status})
        self._log_customer_action(customer_id, "状态变更", f"客户状态更新为：{status}。")

    def update_note(self, customer_id: int, note: str) -> None:
        self._update_customer(customer_id, {"note": note})
        self._log_customer_action(customer_id, "备注更新", "人工备注已更新。")

    def update_contact_email(self, customer_id: int, contact_email: str) -> None:
        email = contact_email.strip()
        self._update_customer(customer_id, {"contact_email": email})
        self._log_customer_action(customer_id, "收件邮箱更新", f"默认收件邮箱更新为：{email or '-'}。")

    def update_manual_research_note(self, customer_id: int, manual_research_note: str) -> None:
        note = manual_research_note.strip()
        self._update_customer(customer_id, {"manual_research_note": note})
        self._log_customer_action(customer_id, "人工特征更新", "人工补充客户特征已保存。")

    def update_tags(self, customer_id: int, tags_text: str) -> None:
        tags = [item.strip() for item in tags_text.split(",") if item.strip()]
        unique_tags = list(dict.fromkeys(tags))
        self._update_customer(customer_id, {"customer_tags": unique_tags})
        self._log_customer_action(
            customer_id,
            "客户标签更新",
            f"当前标签：{', '.join(unique_tags) if unique_tags else '-'}。",
        )

    def update_draft(
        self,
        customer_id: int,
        subject: str,
        body: str,
        review_note: str,
        *,
        ai_tone_risk: str | None = None,
    ) -> None:
        self._update_customer(
            customer_id,
            {
                "email_subject": subject,
                "email_body": body,
                "draft_review_note": review_note,
                "email_ai_tone_risk": ai_tone_risk or "",
                "draft_review_status": DRAFT_STATUS_PENDING,
                "approved_at": "",
            },
        )
        self._log_customer_action(customer_id, "草稿更新", "邮件草稿已人工修改，等待重新审核。")

    def approve_draft(self, customer_id: int, review_note: str = "") -> None:
        updates: dict[str, Any] = {
            "status": STATUS_DRAFTED,
            "draft_review_status": DRAFT_STATUS_APPROVED,
            "approved_at": self._now(),
            "last_send_status": "",
            "last_send_error": "",
        }
        if review_note:
            updates["draft_review_note"] = review_note
        self._update_customer(customer_id, updates)
        self._log_customer_action(customer_id, "人工审核通过", "邮件草稿已通过人工审核。")

    def record_send_result(
        self,
        customer_id: int,
        *,
        recipient_email: str,
        ok: bool,
        error: str = "",
    ) -> None:
        customer = self.get_customer(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")
        now = self._now()
        send_history = list(customer.get("send_history") or [])
        send_history.append(
            {
                "sent_at": now,
                "recipient_email": recipient_email,
                "subject": customer.get("email_subject", ""),
                "status_before_send": customer.get("status", ""),
                "ok": ok,
                "error": error,
            }
        )
        updates: dict[str, Any] = {
            "contact_email": recipient_email,
            "last_send_status": "success" if ok else "failed",
            "last_send_error": error,
            "send_history": send_history,
        }
        if ok:
            updates["status"] = STATUS_SENT
            updates["last_contact_date"] = now
        self._update_customer(customer_id, updates)
        self._log_customer_action(
            customer_id,
            "正式发送" if ok else "发送失败",
            f"收件人：{recipient_email}。{error if error else '邮件已成功发出。'}",
        )

    def record_reply_outcome(
        self,
        customer_id: int,
        *,
        reply_status: str,
        note: str = "",
    ) -> None:
        now = self._now()
        updates: dict[str, Any] = {
            "reply_status": reply_status,
            "last_reply_at": now,
        }
        if reply_status == REPLY_STATUS_REPLIED:
            updates["status"] = STATUS_REPLIED
        elif reply_status == REPLY_STATUS_AUTO_REPLY:
            updates["status"] = STATUS_FOLLOWING
        elif reply_status in {REPLY_STATUS_BOUNCED, REPLY_STATUS_REJECTED}:
            updates["status"] = STATUS_INVALID
        if reply_status == REPLY_STATUS_REJECTED:
            updates["do_not_contact"] = True

        if note.strip():
            customer = self.get_customer(customer_id) or {}
            prior = str(customer.get("note", "")).strip()
            merged = f"{prior}\n[Reply] {note.strip()}".strip() if prior else f"[Reply] {note.strip()}"
            updates["note"] = merged

        self._update_customer(customer_id, updates)
        self._log_customer_action(
            customer_id,
            "回复回写",
            f"回复结果：{reply_status}。{note.strip() or '已更新客户状态。'}",
        )

    def delete_customer(self, customer_id: int) -> None:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM customers WHERE id = ?",
                (int(customer_id),),
            )
            conn.commit()
        if cursor.rowcount == 0:
            raise ValueError(f"Customer {customer_id} not found")

    def _log_customer_action(self, customer_id: int, action: str, detail: str) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM customers WHERE id = ?",
                (int(customer_id),),
            ).fetchone()
            if not row:
                raise ValueError(f"Customer {customer_id} not found")
            customer = self._decode_payload(row["payload"])
            self._append_log(customer, action, detail)
            self._save_customer_payload(conn, int(customer_id), customer)

    def _append_log(self, customer: dict[str, Any], action: str, detail: str) -> None:
        logs = list(customer.get("activity_log") or [])
        logs.append(
            {
                "at": self._now(),
                "action": action,
                "detail": detail,
            }
        )
        customer["activity_log"] = logs[-60:]

    def _serialize_snapshot(self, snapshot: WebsiteSnapshot) -> dict[str, Any]:
        pages = []
        for page in snapshot.pages[:8]:
            preview = page.text[:220].strip() if page.text else ""
            pages.append(
                {
                    "url": page.url,
                    "title": page.title,
                    "page_type": page.page_type,
                    "preview": preview,
                    "blocks": page.blocks[:5],
                }
            )
        return {
            "website": snapshot.website,
            "success": snapshot.success,
            "error": snapshot.error,
            "email_candidates": snapshot.email_candidates[:10],
            "page_count": len(snapshot.pages),
            "pages": pages,
        }

    def _update_customer(self, customer_id: int, updates: dict[str, Any]) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM customers WHERE id = ?",
                (int(customer_id),),
            ).fetchone()
            if not row:
                raise ValueError(f"Customer {customer_id} not found")
            customer = self._decode_payload(row["payload"])
            customer.update(updates)
            self._save_customer_payload(conn, int(customer_id), customer)

    def _save_customer_payload(
        self,
        conn: sqlite3.Connection,
        customer_id: int,
        customer: dict[str, Any],
    ) -> None:
        customer["updated_at"] = self._now()
        conn.execute(
            """
            UPDATE customers
            SET place_id = ?, dedupe_key = ?, company_name = ?, country = ?, updated_at = ?, payload = ?
            WHERE id = ?
            """,
            (
                customer.get("place_id", ""),
                customer.get("dedupe_key", ""),
                customer.get("company_name", ""),
                customer.get("country", ""),
                customer.get("updated_at", ""),
                self._encode_payload(customer),
                int(customer_id),
            ),
        )
        conn.commit()

    def _insert_customer_payload(self, conn: sqlite3.Connection, customer: dict[str, Any]) -> int:
        cursor = conn.execute(
            """
            INSERT INTO customers(place_id, dedupe_key, company_name, country, updated_at, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                customer.get("place_id", ""),
                customer.get("dedupe_key", ""),
                customer.get("company_name", ""),
                customer.get("country", ""),
                customer.get("updated_at", ""),
                self._encode_payload(customer),
            ),
        )
        customer_id = int(cursor.lastrowid)
        customer["id"] = customer_id
        conn.execute(
            """
            UPDATE customers
            SET payload = ?
            WHERE id = ?
            """,
            (self._encode_payload(customer), customer_id),
        )
        conn.commit()
        return customer_id

    def _migrate_legacy_json_if_needed(self) -> None:
        candidates = [
            self.db_path.with_suffix(".json"),
            self.db_path.parent / "mvp_customers.json",
        ]
        legacy_path = next(
            (candidate for candidate in candidates if candidate.exists() and candidate != self.db_path),
            None,
        )
        if legacy_path is None:
            return
        with self._connect() as conn:
            existing = conn.execute("SELECT COUNT(*) AS count FROM customers").fetchone()["count"]
        if int(existing) > 0:
            return
        try:
            store = json.loads(legacy_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        customers = list(store.get("customers", []))
        saved_searches = list(store.get("saved_searches", []))
        smtp = dict(store.get("app_settings", {}).get("smtp", {}) or {})
        with self._connect() as conn:
            for customer in customers:
                normalized = self._normalize_for_storage(customer)
                customer_id = int(normalized.get("id") or 0)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO customers
                    (id, place_id, dedupe_key, company_name, country, updated_at, payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        customer_id or None,
                        normalized.get("place_id", ""),
                        normalized.get("dedupe_key", ""),
                        normalized.get("company_name", ""),
                        normalized.get("country", ""),
                        normalized.get("updated_at", self._now()),
                        self._encode_payload(normalized),
                    ),
                )
            for search in saved_searches:
                payload = dict(search)
                search_id = int(payload.get("id") or 0)
                payload.setdefault("updated_at", self._now())
                conn.execute(
                    """
                    INSERT OR REPLACE INTO saved_searches
                    (id, dedupe_key, updated_at, payload)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        search_id or None,
                        payload.get("dedupe_key", ""),
                        payload.get("updated_at", self._now()),
                        self._encode_payload(payload),
                    ),
                )
            if smtp:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO app_settings(key, value)
                    VALUES (?, ?)
                    """,
                    ("smtp", self._encode_payload(smtp)),
                )
            conn.commit()

    def _normalize_for_storage(self, customer: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(customer)
        normalized.setdefault("id", 0)
        normalized.setdefault("place_id", "")
        normalized.setdefault("company_name", "")
        normalized.setdefault("country", "")
        normalized.setdefault("city", "")
        normalized.setdefault("address", "")
        normalized.setdefault("website", "")
        normalized.setdefault("phone", "")
        normalized.setdefault("contact_email", "")
        normalized.setdefault("email_candidates", [])
        normalized.setdefault("industry", "")
        normalized.setdefault("search_keyword", "")
        normalized.setdefault("source_platform", "google_places")
        normalized.setdefault(
            "dedupe_key",
            f"{str(normalized.get('company_name', '')).lower().strip()}::"
            f"{str(normalized.get('country', '')).lower().strip()}",
        )
        normalized.setdefault("status", STATUS_NEW)
        normalized.setdefault("website_summary", "")
        normalized.setdefault("main_products", [])
        normalized.setdefault("customer_type", "")
        normalized.setdefault("personalization_points", [])
        normalized.setdefault("source_url", "")
        normalized.setdefault("source_snippet", "")
        normalized.setdefault("confidence_score", None)
        normalized.setdefault("review_required", False)
        normalized.setdefault("extraction_status", "")
        normalized.setdefault("profile_json", {})
        normalized.setdefault("email_subject", "")
        normalized.setdefault("email_body", "")
        normalized.setdefault("email_basis", [])
        normalized.setdefault("email_ai_tone_risk", "")
        normalized.setdefault("draft_review_status", DRAFT_STATUS_PENDING)
        normalized.setdefault("draft_review_note", "")
        normalized.setdefault("approved_at", "")
        normalized.setdefault("last_send_status", "")
        normalized.setdefault("last_send_error", "")
        normalized.setdefault("send_history", [])
        normalized.setdefault("reply_status", "")
        normalized.setdefault("last_reply_at", "")
        normalized.setdefault("do_not_contact", False)
        normalized.setdefault("manual_research_note", "")
        normalized.setdefault("customer_tags", [])
        normalized.setdefault("crawl_snapshot", {})
        normalized.setdefault("activity_log", [])
        normalized.setdefault("note", "")
        normalized.setdefault("owner", "")
        normalized.setdefault("last_contact_date", "")
        normalized.setdefault("next_follow_up_date", "")
        normalized.setdefault("created_at", self._now())
        normalized.setdefault("updated_at", normalized.get("created_at") or self._now())
        return normalized

    def _new_customer_payload(self, lead: Lead, *, dedupe_key: str, now: str) -> dict[str, Any]:
        return self._normalize_for_storage(
            {
                "id": 0,
                "place_id": lead.place_id,
                "company_name": lead.company_name,
                "country": lead.country,
                "city": lead.city,
                "address": lead.address,
                "website": lead.website,
                "phone": lead.phone,
                "contact_email": "",
                "email_candidates": [],
                "industry": lead.industry,
                "search_keyword": lead.search_keyword,
                "source_platform": lead.source_platform,
                "dedupe_key": dedupe_key,
                "status": STATUS_NEW,
                "website_summary": "",
                "main_products": [],
                "customer_type": "",
                "personalization_points": [],
                "source_url": "",
                "source_snippet": "",
                "confidence_score": None,
                "review_required": False,
                "extraction_status": "",
                "profile_json": {},
                "email_subject": "",
                "email_body": "",
                "email_basis": [],
                "email_ai_tone_risk": "",
                "draft_review_status": DRAFT_STATUS_PENDING,
                "draft_review_note": "",
                "approved_at": "",
                "last_send_status": "",
                "last_send_error": "",
                "send_history": [],
                "reply_status": "",
                "last_reply_at": "",
                "do_not_contact": False,
                "manual_research_note": "",
                "customer_tags": [],
                "crawl_snapshot": {},
                "activity_log": [],
                "note": "",
                "owner": "",
                "last_contact_date": "",
                "next_follow_up_date": "",
                "created_at": now,
                "updated_at": now,
            }
        )

    def _connect(self) -> sqlite3.Connection:
        self._cleanup_stale_sqlite_files()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA journal_mode={self._pragma_value(self.journal_mode, kind='journal')}")
        conn.execute(f"PRAGMA synchronous={self._pragma_value(self.synchronous)}")
        return conn

    def _reset_broken_db_file(self) -> None:
        if self.db_path.exists():
            backup = self.db_path.with_name(
                f"{self.db_path.stem}.broken-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{self.db_path.suffix}"
            )
            try:
                self.db_path.replace(backup)
            except PermissionError:
                self.db_path.unlink(missing_ok=True)
        journal_path = self.db_path.with_name(f"{self.db_path.name}-journal")
        if journal_path.exists():
            journal_path.unlink()

    def _cleanup_stale_sqlite_files(self) -> None:
        journal_path = self.db_path.with_name(f"{self.db_path.name}-journal")
        if self.db_path.exists() and self.db_path.stat().st_size == 0:
            self.db_path.unlink(missing_ok=True)
        if journal_path.exists() and (
            not self.db_path.exists() or self.db_path.stat().st_size == 0
        ):
            journal_path.unlink(missing_ok=True)

    def _pragma_value(self, value: str, *, kind: str = "sync") -> str:
        normalized = (value or "").strip().upper()
        if normalized in {"DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF", "NORMAL", "FULL", "EXTRA"}:
            return normalized
        return "MEMORY" if kind == "journal" else "OFF"

    def _get_app_setting_payload(self, key: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (key,),
            ).fetchone()
        return self._decode_payload(row["value"]) if row else {}

    def _save_app_setting_payload(self, key: str, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings(key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, self._encode_payload(payload)),
            )
            conn.commit()

    def _deep_merge(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in dict(override or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._deep_merge(dict(merged[key]), value)
            else:
                merged[key] = value
        return merged

    def _encode_payload(self, payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False)

    def _decode_payload(self, payload: str) -> dict[str, Any]:
        return json.loads(payload)

    def _normalize(self, customer: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_for_storage(customer)
        normalized["review_required"] = bool(normalized.get("review_required"))
        normalized["note"] = self._clean_placeholder_text(normalized.get("note", ""))
        normalized["draft_review_note"] = self._clean_placeholder_text(
            normalized.get("draft_review_note", "")
        )
        normalized["manual_research_note"] = self._clean_placeholder_text(
            normalized.get("manual_research_note", "")
        )
        normalized["customer_tags"] = self._clean_placeholder_tags(
            normalized.get("customer_tags", [])
        )
        normalized["activity_log"] = self._normalize_activity_log(
            normalized,
            normalized.get("activity_log", []),
        )
        normalized.update(self._build_match_profile(normalized))
        return normalized

    def _build_match_profile(self, customer: dict[str, Any]) -> dict[str, Any]:
        text_blob = " ".join(
            [
                str(customer.get("customer_type", "")),
                str(customer.get("industry", "")),
                str(customer.get("website_summary", "")),
                str(customer.get("manual_research_note", "")),
                str(customer.get("search_keyword", "")),
                " ".join(customer.get("main_products", []) or []),
                " ".join(customer.get("customer_tags", []) or []),
            ]
        ).lower()
        status = str(customer.get("status", ""))

        score = 50
        reasons: list[str] = []

        if any(token in text_blob for token in ("private label", "oem", "odm", "eigenmarke")):
            score += 22
            reasons.append("有私牌或定制合作信号")

        if any(
            token in text_blob
            for token in (
                "importer",
                "distributor",
                "wholesaler",
                "supplier",
                "dealer",
                "reseller",
                "procurement",
                "brand owner",
            )
        ):
            score += 18
            reasons.append("更像渠道商、进口商或品牌项目客户")

        if any(
            token in text_blob
            for token in (
                "silicone",
                "spatula",
                "scraper",
                "brush",
                "baking",
                "bakeware",
                "kitchen accessories",
                "kitchen tools",
                "housewares",
                "utensils",
            )
        ):
            score += 16
            reasons.append("产品方向和厨房工具或硅胶用品较相关")

        if any(
            token in text_blob
            for token in (
                "clear communication",
                "stable quality",
                "reliable lead times",
                "professional supplier",
            )
        ):
            score += 6

        confidence = customer.get("confidence_score")
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            confidence_value = None
        if confidence_value is not None:
            if confidence_value >= 0.8:
                score += 6
            elif confidence_value < 0.55:
                score -= 6

        if any(
            token in text_blob
            for token in (
                "commercial kitchen",
                "grosskuch",
                "gastronomie",
                "catering equipment",
                "machinery",
                "refrigeration",
                "ventilation",
                "food processing",
            )
        ):
            score -= 24
            reasons.append("更偏商厨大设备或非目标方向")

        if any(
            token in text_blob
            for token in (
                "furniture_store",
                "home_goods_store",
                "home_improvement_store",
                "retail",
                "shop",
                "store",
            )
        ):
            score -= 18
            reasons.append("更像零售门店或终端消费场景")

        if status == STATUS_INVALID:
            score -= 35
            reasons.append("已被判定为无效客户")

        score = max(0, min(100, score))
        if score >= 75:
            level = "高匹配"
            summary = "更符合你们当前产品线和合作方向，可优先跟进。"
        elif score >= 55:
            level = "中匹配"
            summary = "方向基本相关，但还需要结合官网和采购模式再人工复核。"
        else:
            level = "低匹配"
            summary = "和当前产品线或合作模式的匹配度偏低，建议谨慎投入时间。"

        if reasons:
            summary = f"{summary} 主要依据：{'；'.join(reasons[:2])}。"

        return {
            "match_score": score,
            "match_level": level,
            "match_summary": summary,
            "match_reasons": reasons,
        }

    def _now(self) -> str:
        return datetime.utcnow().isoformat(timespec="seconds")

    def _clean_placeholder_text(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        stripped = text.replace("?", "").replace("/", "").replace("-", "").replace(",", "").strip()
        if not stripped:
            return ""
        return text

    def _clean_placeholder_tags(self, tags: Any) -> list[str]:
        cleaned: list[str] = []
        for tag in list(tags or []):
            item = self._clean_placeholder_text(tag)
            if item:
                cleaned.append(item)
        return list(dict.fromkeys(cleaned))

    def _normalize_activity_log(
        self,
        customer: dict[str, Any],
        logs: Any,
    ) -> list[dict[str, Any]]:
        normalized_logs: list[dict[str, Any]] = []
        current_tags = ", ".join(customer.get("customer_tags", []) or [])
        for entry in list(logs or []):
            action = self._clean_placeholder_text(entry.get("action", ""))
            detail = self._clean_placeholder_text(entry.get("detail", ""))
            if not action and not detail:
                continue
            if action == "客户标签更新" and not detail:
                detail = f"当前标签：{current_tags or '-'}。"
            elif action == "备注更新" and not detail:
                detail = "人工备注已更新。"
            elif action == "人工特征更新" and not detail:
                detail = "人工补充客户特征已保存。"
            if not action:
                action = "历史记录"
            normalized_logs.append(
                {
                    "at": entry.get("at", ""),
                    "action": action,
                    "detail": detail or "-",
                }
            )
        return normalized_logs

    def _normalize_api_token_row(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = dict(row)
        scopes_raw = data.get("scopes", "[]")
        try:
            scopes = json.loads(scopes_raw) if isinstance(scopes_raw, str) else list(scopes_raw or [])
        except json.JSONDecodeError:
            scopes = []
        return {
            "id": int(data.get("id", 0)),
            "token_prefix": str(data.get("token_prefix", "")),
            "token_name": str(data.get("token_name", "")),
            "status": str(data.get("status", "")),
            "scopes": [str(item).strip() for item in scopes if str(item).strip()],
            "note": str(data.get("note", "")),
            "created_at": str(data.get("created_at", "")),
            "updated_at": str(data.get("updated_at", "")),
            "expires_at": str(data.get("expires_at", "")),
            "last_used_at": str(data.get("last_used_at", "")),
        }

    def _hash_token(self, raw_token: str) -> str:
        return hashlib.sha256(str(raw_token or "").encode("utf-8")).hexdigest()
