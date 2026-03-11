"""Import all models so SQLAlchemy can detect them."""

from app.models.admin_membership import AdminMembership  # noqa: F401
from app.models.base import Base, BaseModel  # noqa: F401
from app.models.blackboard import Blackboard  # noqa: F401
from app.models.circuit_state import CircuitState  # noqa: F401
from app.models.cluster import Cluster  # noqa: F401
from app.models.corridor import CorridorHex, HexConnection  # noqa: F401
from app.models.dead_letter import DeadLetter  # noqa: F401
from app.models.decision_record import DecisionRecord  # noqa: F401
from app.models.delivery_log import DeliveryLog  # noqa: F401
from app.models.deploy_record import DeployRecord  # noqa: F401
from app.models.event_log import EventLog  # noqa: F401
from app.models.gene import (  # noqa: F401
    Gene,
    GeneEffectLog,
    GeneRating,
    Genome,
    GenomeRating,
    InstanceGene,
)
from app.models.idempotency_cache import IdempotencyCache  # noqa: F401
from app.models.instance import Instance  # noqa: F401
from app.models.instance_template import InstanceTemplate  # noqa: F401
from app.models.instance_mcp_server import InstanceMcpServer  # noqa: F401
from app.models.instance_member import InstanceMember  # noqa: F401
from app.models.llm_usage_log import LlmUsageLog  # noqa: F401
from app.models.message_queue import MessageQueueItem  # noqa: F401
from app.models.message_schema import MessageSchema  # noqa: F401
from app.models.node_card import NodeCard  # noqa: F401
from app.models.node_type import NodeTypeDefinition  # noqa: F401
from app.models.org_llm_key import OrgLlmKey  # noqa: F401
from app.models.org_required_gene import OrgRequiredGene  # noqa: F401
from app.models.org_smtp_config import OrgSmtpConfig  # noqa: F401
from app.models.oauth_connection import UserOAuthConnection  # noqa: F401
from app.models.operation_audit_log import OperationAuditLog  # noqa: F401
from app.models.org_membership import OrgMembership  # noqa: F401
from app.models.org_oauth_binding import OrgOAuthBinding  # noqa: F401
from app.models.organization import Organization  # noqa: F401
from app.models.sse_connection import SSEConnection  # noqa: F401
from app.models.system_config import SystemConfig  # noqa: F401
from app.models.trust_policy import TrustPolicy  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.user_llm_config import UserLlmConfig  # noqa: F401
from app.models.user_llm_key import UserLlmKey  # noqa: F401
from app.models.workspace import Workspace  # noqa: F401
from app.models.workspace_agent import WorkspaceAgent  # noqa: F401
from app.models.workspace_file import WorkspaceFile  # noqa: F401
from app.models.workspace_member import WorkspaceMember  # noqa: F401
from app.models.workspace_message import WorkspaceMessage  # noqa: F401
from app.models.workspace_objective import WorkspaceObjective  # noqa: F401
from app.models.workspace_schedule import WorkspaceSchedule  # noqa: F401
from app.models.workspace_task import WorkspaceTask  # noqa: F401
from app.models.workspace_template import WorkspaceTemplate  # noqa: F401
