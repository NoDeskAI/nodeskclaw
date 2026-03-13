"""Built-in security plugins — registered via loader.register_builtin()."""

from ..loader import register_builtin
from .approval_channel import ApprovalChannelPlugin
from .audit_logger import AuditLoggerPlugin
from .dlp_scanner import DlpScannerPlugin
from .policy_gate import PolicyGatePlugin

register_builtin("policy-gate", PolicyGatePlugin)
register_builtin("dlp-scanner", DlpScannerPlugin)
register_builtin("audit-logger", AuditLoggerPlugin)
register_builtin("approval-channel", ApprovalChannelPlugin)
