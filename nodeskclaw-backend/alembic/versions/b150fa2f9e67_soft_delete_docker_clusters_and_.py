"""soft_delete_docker_clusters_and_instances

Revision ID: b150fa2f9e67
Revises: 9b871b5cc694
Create Date: 2026-07-02 16:59:00.785492

"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b150fa2f9e67'
down_revision: str | Sequence[str] | None = '9b871b5cc694'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Docker 类型集群功能已移除，软删除存量 docker 集群及其关联实例。

    宿主机上仍在运行的 docker-{slug} compose 项目不受影响，需手动清理。
    """
    op.execute(
        "UPDATE instances SET deleted_at = NOW() WHERE deleted_at IS NULL "
        "AND (compute_provider = 'docker' OR cluster_id IN "
        "(SELECT id FROM clusters WHERE compute_provider = 'docker'))"
    )
    op.execute(
        "UPDATE clusters SET deleted_at = NOW() WHERE deleted_at IS NULL "
        "AND compute_provider = 'docker'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    pass
