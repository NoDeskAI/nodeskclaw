"""Import all models so SQLAlchemy can detect them."""

from app.models.base import Base, BaseModel  # noqa: F401
from app.models.cluster import Cluster  # noqa: F401
from app.models.deploy_record import DeployRecord  # noqa: F401
from app.models.instance import Instance  # noqa: F401
from app.models.org_membership import OrgMembership  # noqa: F401
from app.models.organization import Organization  # noqa: F401
from app.models.plan import Plan  # noqa: F401
from app.models.system_config import SystemConfig  # noqa: F401
from app.models.user import User  # noqa: F401
