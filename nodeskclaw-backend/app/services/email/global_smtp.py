"""GlobalSmtpTransport — CE 全局 SMTP 配置。

从系统配置表（config）读取全局 SMTP 参数，所有用户共用。
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.email.transport import EmailTransport, SmtpConfig

logger = logging.getLogger(__name__)


class GlobalSmtpTransport(EmailTransport):

    async def resolve_smtp_config(
        self, db: AsyncSession, email: str,
    ) -> SmtpConfig | None:
        from app.services.config_service import get_config

        host = await get_config("smtp_host", db)
        if not host:
            logger.debug("全局 SMTP 未配置")
            return None

        port_str = await get_config("smtp_port", db) or "587"
        username = await get_config("smtp_username", db) or ""
        password = await get_config("smtp_password", db) or ""
        from_email = await get_config("smtp_from_email", db) or username
        from_name = await get_config("smtp_from_name", db)
        use_tls_str = await get_config("smtp_use_tls", db)
        use_tls = use_tls_str != "false" if use_tls_str else True

        return SmtpConfig(
            smtp_host=host,
            smtp_port=int(port_str),
            smtp_username=username,
            smtp_password=password,
            from_email=from_email,
            from_name=from_name,
            use_tls=use_tls,
        )
