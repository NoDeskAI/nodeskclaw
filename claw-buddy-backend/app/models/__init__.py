"""Import all models so SQLAlchemy can detect them."""

from app.models.base import Base, BaseModel  # noqa: F401
from app.models.agent_share_config import AgentShareConfig  # noqa: F401
from app.models.agent_subscription import AgentSubscription  # noqa: F401
from app.models.blackboard import Blackboard  # noqa: F401
from app.models.cluster import Cluster  # noqa: F401
from app.models.context_entry import ContextEntry  # noqa: F401
from app.models.deploy_record import DeployRecord  # noqa: F401
from app.models.instance import Instance  # noqa: F401
from app.models.llm_usage_log import LlmUsageLog  # noqa: F401
from app.models.org_llm_key import OrgLlmKey  # noqa: F401
from app.models.org_membership import OrgMembership  # noqa: F401
from app.models.organization import Organization  # noqa: F401
from app.models.plan import Plan  # noqa: F401
from app.models.system_config import SystemConfig  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.user_llm_config import UserLlmConfig  # noqa: F401
from app.models.user_llm_key import UserLlmKey  # noqa: F401
from app.models.workspace import Workspace  # noqa: F401
from app.models.workspace_member import WorkspaceMember  # noqa: F401
