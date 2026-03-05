"""EmailTransport 工厂 — 根据 edition 返回对应邮件传输实现。"""

from __future__ import annotations

from functools import lru_cache

from app.services.email.transport import EmailTransport


@lru_cache(maxsize=1)
def get_email_transport() -> EmailTransport:
    from app.core.feature_gate import feature_gate

    if feature_gate.is_ee:
        try:
            from ee.backend.services.email.org_smtp import OrgSmtpTransport
            return OrgSmtpTransport()
        except ImportError:
            pass

    from app.services.email.global_smtp import GlobalSmtpTransport
    return GlobalSmtpTransport()
