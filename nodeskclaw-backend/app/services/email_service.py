"""Email sending service — 统一通过全局 SMTP 配置发送邮件。"""

import logging
from email.message import EmailMessage

import aiosmtplib
from sqlalchemy.ext.asyncio import AsyncSession

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

    is_implicit_tls = smtp_config.use_tls and smtp_config.smtp_port == 465
    await aiosmtplib.send(
        msg,
        hostname=smtp_config.smtp_host,
        port=smtp_config.smtp_port,
        username=smtp_config.smtp_username,
        password=smtp_config.smtp_password,
        use_tls=is_implicit_tls,
        start_tls=smtp_config.use_tls and not is_implicit_tls,
        timeout=15,
    )
    logger.info("Email sent to %s via %s:%s", to_email, smtp_config.smtp_host, smtp_config.smtp_port)


async def send_verification_email(
    to_email: str, code: str, smtp_config: SmtpConfig,
    db: AsyncSession | None = None,
) -> None:
    subject = VERIFICATION_EMAIL_SUBJECT
    template = VERIFICATION_EMAIL_HTML

    if db is not None:
        from app.services.config_service import get_config
        custom_subject = await get_config("verification_email_subject", db)
        custom_template = await get_config("verification_email_template", db)
        if custom_subject:
            subject = custom_subject
        if custom_template:
            template = custom_template

    html = template.replace("{code}", code)
    await _send_email(to_email, subject, html, smtp_config)


async def send_test_email(
    to_email: str, smtp_config: SmtpConfig,
) -> None:
    await _send_email(to_email, TEST_EMAIL_SUBJECT, TEST_EMAIL_HTML, smtp_config)


async def get_smtp_config_for_email(
    db: AsyncSession, email: str,
) -> SmtpConfig | None:
    """读取全局 SMTP 配置。email 参数保留用于接口兼容。"""
    from app.services.email.global_smtp import GlobalSmtpTransport
    transport = GlobalSmtpTransport()
    return await transport.resolve_smtp_config(db, email)


INVITATION_EMAIL_SUBJECT = "DeskClaw - {org_name}"

INVITATION_EMAIL_HTML = """\
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 480px; margin: 0 auto; padding: 20px;">
  <div style="text-align: center; padding: 20px 0; border-bottom: 1px solid #e5e7eb;">
    <h2 style="margin: 0; color: #111827;">DeskClaw</h2>
  </div>
  <div style="padding: 32px 0;">
    <p style="color: #374151; font-size: 15px; line-height: 1.6;">
      <strong>{inviter_name}</strong> has invited you to join <strong>{org_name}</strong> as <strong>{role}</strong>.
    </p>
    <div style="text-align: center; margin: 24px 0;">
      <a href="{invite_url}"
         style="display: inline-block; padding: 12px 32px; background: #111827; color: #ffffff; font-size: 15px; font-weight: 600; text-decoration: none; border-radius: 8px;">
        Accept Invitation
      </a>
    </div>
    <p style="color: #6b7280; font-size: 13px; line-height: 1.6;">
      This invitation expires in 7 days. If you did not expect this email, you can safely ignore it.
    </p>
  </div>
  <div style="border-top: 1px solid #e5e7eb; padding-top: 16px; text-align: center;">
    <p style="color: #9ca3af; font-size: 12px;">DeskClaw - AI Cloud Deployment Platform</p>
  </div>
</body>
</html>
"""


async def send_invitation_email(
    to_email: str,
    org_name: str,
    inviter_name: str,
    invite_url: str,
    role: str,
    db: AsyncSession,
    org_id: str | None = None,
    inviter_id: str | None = None,
) -> None:
    """Send an invitation email. If SMTP is not configured, raises an exception."""
    from app.services.email.factory import get_email_transport

    if not org_name and org_id and db:
        from app.models.organization import Organization
        from sqlalchemy import select
        org = (await db.execute(select(Organization).where(Organization.id == org_id, Organization.deleted_at.is_(None)))).scalar_one_or_none()
        if org:
            org_name = org.name

    if not inviter_name and inviter_id and db:
        from app.models.user import User
        from sqlalchemy import select as sel
        user = (await db.execute(sel(User).where(User.id == inviter_id, User.deleted_at.is_(None)))).scalar_one_or_none()
        if user:
            inviter_name = user.name or user.email

    transport = get_email_transport()
    smtp_config = await transport.resolve_smtp_config(db, to_email)
    if smtp_config is None:
        raise RuntimeError("SMTP not configured")

    subject = INVITATION_EMAIL_SUBJECT.replace("{org_name}", org_name or "DeskClaw")
    html = (
        INVITATION_EMAIL_HTML
        .replace("{inviter_name}", inviter_name or "Admin")
        .replace("{org_name}", org_name or "DeskClaw")
        .replace("{role}", role)
        .replace("{invite_url}", invite_url)
    )
    await _send_email(to_email, subject, html, smtp_config)
