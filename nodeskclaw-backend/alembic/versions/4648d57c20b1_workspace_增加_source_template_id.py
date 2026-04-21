"""workspace 增加 source_template_id

Revision ID: 4648d57c20b1
Revises: d9017e4ff2a0
Create Date: 2026-04-21 11:46:36.890819

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '4648d57c20b1'
down_revision: Union[str, Sequence[str], None] = 'd9017e4ff2a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('workspaces', sa.Column('source_template_id', sa.String(length=36), nullable=True))
    op.create_index(op.f('ix_workspaces_source_template_id'), 'workspaces', ['source_template_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_workspaces_source_template_id'), table_name='workspaces')
    op.drop_column('workspaces', 'source_template_id')
