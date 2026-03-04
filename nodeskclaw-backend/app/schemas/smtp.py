"""SMTP configuration schemas."""

from pydantic import BaseModel


class SmtpConfigCreate(BaseModel):
    smtp_host: str
    smtp_port: int = 587
    smtp_username: str
    smtp_password: str
    from_email: str
    from_name: str | None = None
    use_tls: bool = True


class SmtpConfigResponse(BaseModel):
    id: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password_masked: str
    from_email: str
    from_name: str | None
    use_tls: bool

    model_config = {"from_attributes": True}


class SmtpTestRequest(BaseModel):
    recipient_email: str
