"""Email sending service — 通过 EmailTransport 抽象解耦 SMTP 配置来源。

CE: 全局 SMTP（GlobalSmtpTransport）
EE: 组织级 SMTP（OrgSmtpTransport）
"""

import logging
from email.message import EmailMessage

import aiosmtplib
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.email.factory import get_email_transport
from app.services.email.transport import SmtpConfig

logger = logging.getLogger(__name__)

VERIFICATION_EMAIL_SUBJECT = "DeskClaw - 登录验证码"

VERIFICATION_EMAIL_HTML = """\
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 480px; margin: 0 auto; padding: 20px;">
  <div style="text-align: center; padding: 20px 0; border-bottom: 1px solid #e5e7eb;">
    <h2 style="margin: 0; color: #111827;">DeskClaw</h2>
  </div>
  <div style="padding: 32px 0;">
    <p style="color: #374151; font-size: 15px; line-height: 1.6;">
      你正在登录 DeskClaw，验证码为：
    </p>
    <div style="text-align: center; margin: 24px 0;">
      <span style="display: inline-block; font-size: 32px; font-weight: 700; letter-spacing: 8px; color: #111827; background: #f3f4f6; padding: 12px 24px; border-radius: 8px;">
        {code}
      </span>
    </div>
    <p style="color: #6b7280; font-size: 13px; line-height: 1.6;">
      验证码 5 分钟内有效。如果你没有进行此操作，请忽略这封邮件。
    </p>
  </div>
  <div style="border-top: 1px solid #e5e7eb; padding-top: 16px; text-align: center;">
    <p style="color: #9ca3af; font-size: 12px;">DeskClaw - AI Cloud Deployment Platform</p>
  </div>
</body>
</html>
"""

TEST_EMAIL_SUBJECT = "DeskClaw - SMTP 测试邮件"
TEST_EMAIL_HTML = """\
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 480px; margin: 0 auto; padding: 20px;">
  <div style="text-align: center; padding: 32px 0;">
    <h2 style="color: #111827; margin-bottom: 16px;">SMTP 配置测试成功</h2>
    <p style="color: #6b7280; font-size: 14px;">
      如果你收到了这封邮件，说明 SMTP 配置正确。
    </p>
  </div>
</body>
</html>
"""


async def _send_email(
    to_email: str,
    subject: str,
    html_body: str,
    smtp_config: SmtpConfig,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = (
        f"{smtp_config.from_name} <{smtp_config.from_email}>"
        if smtp_config.from_name
        else smtp_config.from_email
    )
    msg["To"] = to_email
    msg.set_content(subject)
    msg.add_alternative(html_body, subtype="html")

    await aiosmtplib.send(
        msg,
        hostname=smtp_config.smtp_host,
        port=smtp_config.smtp_port,
        username=smtp_config.smtp_username,
        password=smtp_config.smtp_password,
        start_tls=smtp_config.use_tls,
    )
    logger.info("Email sent to %s via %s:%s", to_email, smtp_config.smtp_host, smtp_config.smtp_port)


async def send_verification_email(
    to_email: str, code: str, smtp_config: SmtpConfig,
) -> None:
    html = VERIFICATION_EMAIL_HTML.replace("{code}", code)
    await _send_email(to_email, VERIFICATION_EMAIL_SUBJECT, html, smtp_config)


async def send_test_email(
    to_email: str, smtp_config: SmtpConfig,
) -> None:
    await _send_email(to_email, TEST_EMAIL_SUBJECT, TEST_EMAIL_HTML, smtp_config)


async def get_smtp_config_for_email(
    db: AsyncSession, email: str,
) -> SmtpConfig | None:
    """通过 EmailTransport 解析 SMTP 配置（CE: 全局 / EE: 组织级）。"""
    transport = get_email_transport()
    return await transport.resolve_smtp_config(db, email)
