"""EmailTransport 抽象接口 — CE/EE SMTP 配置来源差异。

CE (GlobalSmtpTransport):
  从全局设置（环境变量 / 系统配置表）读取单一 SMTP 配置，
  所有用户共用同一套发件服务器。

EE (OrgSmtpTransport):
  按用户邮箱查找所属组织，返回组织级 SMTP 配置，
  不同组织可配置不同的发件服务器。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class SmtpConfig:
    """SMTP 发件配置（与存储来源无关）。"""

    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    from_email: str
    from_name: str | None = None
    use_tls: bool = True


class EmailTransport(ABC):

    @abstractmethod
    async def resolve_smtp_config(
        self, db: AsyncSession, email: str,
    ) -> SmtpConfig | None:
        """根据收件人邮箱解析 SMTP 配置。

        CE: 忽略 email，返回全局 SMTP 配置
        EE: 通过 email -> user -> org -> OrgSmtpConfig 查找
        """
