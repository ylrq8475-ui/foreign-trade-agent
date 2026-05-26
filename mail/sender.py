from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from typing import Any

from config.settings import Settings
from config.statuses import DRAFT_STATUS_APPROVED
from database.repository import CustomerRepository


class SendValidationError(Exception):
    pass


class ManualSender:
    def __init__(self, repository: CustomerRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    def send(self, customer_id: int, recipient_email: str) -> None:
        customer = self.repository.get_customer(customer_id)
        if not customer:
            raise SendValidationError("Customer not found.")
        recipient_email = recipient_email.strip()
        self._validate_before_send(customer, recipient_email)
        smtp = self._effective_smtp_settings()

        message = EmailMessage()
        message["From"] = formataddr((smtp["from_name"], smtp["from_email"]))
        message["To"] = recipient_email
        message["Subject"] = customer.get("email_subject", "").strip()
        message.set_content(customer.get("email_body", "").strip())

        try:
            with self._open_server(smtp) as server:
                server.send_message(message)
        except Exception as exc:
            self.repository.record_send_result(
                customer_id,
                recipient_email=recipient_email,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise SendValidationError(f"Send failed: {type(exc).__name__}: {exc}") from exc

        self.repository.record_send_result(
            customer_id,
            recipient_email=recipient_email,
            ok=True,
            error="",
        )

    def status_summary(self) -> dict[str, Any]:
        smtp = self._effective_smtp_settings()
        return {
            "configured": bool(smtp["host"] and smtp["from_email"]),
            "host": smtp["host"],
            "port": smtp["port"],
            "security": smtp["security"],
            "auto_send_on_approval": smtp["auto_send_on_approval"],
            "from_email": smtp["from_email"],
            "from_name": smtp["from_name"],
            "user": smtp["user"],
            "has_password": bool(smtp["password"]),
            "source": "website" if smtp.get("_uses_saved_settings") else "env",
        }

    def test_connection(self, smtp_override: dict[str, Any] | None = None) -> None:
        smtp = self._effective_smtp_settings(smtp_override=smtp_override)
        if not smtp["host"] or not smtp["from_email"]:
            raise SendValidationError("SMTP settings are incomplete.")
        with self._open_server(smtp):
            return None

    def send_approved_queue(self, limit: int | None = None) -> dict[str, Any]:
        rows = self.repository.list_customers()
        sent = 0
        failed = 0
        skipped = 0
        errors: list[str] = []

        for customer in rows:
            if limit is not None and sent >= limit:
                break
            if not self._customer_is_send_ready(customer):
                skipped += 1
                continue
            customer_id = int(customer.get("id", 0))
            recipient_email = str(customer.get("contact_email") or "").strip()
            try:
                self.send(customer_id, recipient_email)
                sent += 1
            except SendValidationError as exc:
                failed += 1
                errors.append(f"{customer.get('company_name') or customer_id}: {exc}")

        return {
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
            "errors": errors,
        }

    def _validate_before_send(self, customer: dict, recipient_email: str) -> None:
        if customer.get("do_not_contact"):
            raise SendValidationError("This customer is marked as do not contact.")
        if customer.get("draft_review_status") != DRAFT_STATUS_APPROVED:
            raise SendValidationError("The draft must be manually approved before sending.")
        if not customer.get("email_subject", "").strip():
            raise SendValidationError("Email subject is empty.")
        if not customer.get("email_body", "").strip():
            raise SendValidationError("Email body is empty.")
        if not recipient_email:
            raise SendValidationError("Recipient email is required.")
        if "@" not in parseaddr(recipient_email)[1]:
            raise SendValidationError("Recipient email is invalid.")
        smtp = self._effective_smtp_settings()
        if not smtp["host"] or not smtp["from_email"]:
            raise SendValidationError("SMTP settings are incomplete.")

    def _customer_is_send_ready(self, customer: dict[str, Any]) -> bool:
        if customer.get("do_not_contact"):
            return False
        if customer.get("draft_review_status") != DRAFT_STATUS_APPROVED:
            return False
        if customer.get("last_send_status") == "success":
            return False
        if not str(customer.get("contact_email") or "").strip():
            return False
        if not str(customer.get("email_subject") or "").strip():
            return False
        if not str(customer.get("email_body") or "").strip():
            return False
        return True

    def _smtp_security_mode(self, smtp: dict[str, Any]) -> str:
        mode = str(smtp.get("security", "") or "").strip().lower()
        if mode in {"ssl", "starttls", "none"}:
            return mode
        if int(smtp.get("port") or 0) == 465:
            return "ssl"
        if bool(smtp.get("use_tls")):
            return "starttls"
        return "none"

    def _open_server(self, smtp: dict[str, Any]) -> smtplib.SMTP:
        security = self._smtp_security_mode(smtp)
        timeout = int(smtp.get("timeout_seconds") or 20)
        if security == "ssl":
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                str(smtp["host"]),
                int(smtp["port"]),
                timeout=timeout,
            )
        else:
            server = smtplib.SMTP(
                str(smtp["host"]),
                int(smtp["port"]),
                timeout=timeout,
            )
            if security == "starttls":
                server.starttls()
        if str(smtp.get("user") or "").strip():
            server.login(str(smtp["user"]), str(smtp.get("password") or ""))
        return server

    def _effective_smtp_settings(
        self,
        smtp_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        saved = self.repository.get_smtp_settings()
        uses_saved = any(
            str(saved.get(key) or "").strip()
            for key in ("host", "user", "password", "from_email", "from_name", "security")
        ) or bool(saved.get("port")) or bool(saved.get("timeout_seconds"))
        smtp = {
            "host": saved.get("host") or self.settings.smtp_host,
            "port": int(saved.get("port") or self.settings.smtp_port or 587),
            "user": saved.get("user") or self.settings.smtp_user,
            "password": saved.get("password") or self.settings.smtp_password,
            "from_email": saved.get("from_email") or self.settings.smtp_from_email,
            "from_name": saved.get("from_name") or self.settings.smtp_from_name,
            "security": saved.get("security") or self.settings.smtp_security,
            "use_tls": bool(saved.get("use_tls") if uses_saved else self.settings.smtp_use_tls),
            "timeout_seconds": int(
                saved.get("timeout_seconds") or self.settings.smtp_timeout_seconds or 20
            ),
            "auto_send_on_approval": bool(
                saved.get("auto_send_on_approval")
                if uses_saved
                else self.settings.smtp_auto_send_on_approval
            ),
            "_uses_saved_settings": uses_saved,
        }
        if smtp_override:
            override = dict(smtp_override)
            if not str(override.get("password") or "").strip():
                override["password"] = smtp["password"]
            for key in (
                "host",
                "port",
                "user",
                "password",
                "from_email",
                "from_name",
                "security",
                "use_tls",
                "timeout_seconds",
                "auto_send_on_approval",
            ):
                if key in override and override[key] not in (None, ""):
                    smtp[key] = override[key]
            smtp["_uses_saved_settings"] = False
        return smtp
