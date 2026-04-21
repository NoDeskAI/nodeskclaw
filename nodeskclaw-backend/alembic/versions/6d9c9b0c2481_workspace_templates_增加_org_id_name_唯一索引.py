"""workspace_templates 增加 org_id+name 唯一索引

Revision ID: 6d9c9b0c2481
Revises: 4648d57c20b1
Create Date: 2026-04-21 11:53:10.812852

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '6d9c9b0c2481'
down_revision: Union[str, Sequence[str], None] = '4648d57c20b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        'uq_workspace_templates_org_name', 'workspace_templates',
        ['org_id', 'name'], unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'uq_workspace_templates_org_name', table_name='workspace_templates',
        postgresql_where=sa.text('deleted_at IS NULL'),
    )
