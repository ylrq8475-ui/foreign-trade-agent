from __future__ import annotations


class DraftManager:
    @staticmethod
    def target_status_for_draft(has_body: bool) -> str:
        return "待人工审核" if has_body else "未联系"
