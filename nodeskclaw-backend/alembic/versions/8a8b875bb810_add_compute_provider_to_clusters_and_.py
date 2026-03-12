"""add compute_provider to clusters and fix name unique

Revision ID: 8a8b875bb810
Revises: a349ffaba48f
Create Date: 2026-03-12 14:04:24.114020

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '8a8b875bb810'
down_revision: Union[str, Sequence[str], None] = 'a349ffaba48f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'clusters',
        sa.Column('compute_provider', sa.String(length=32), nullable=False, server_default='k8s'),
    )
    op.drop_constraint('clusters_name_key', 'clusters', type_='unique')
    op.create_index(
        'uq_clusters_name_org', 'clusters', ['name', 'org_id'],
        unique=True, postgresql_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'uq_clusters_name_org', table_name='clusters',
        postgresql_where=sa.text('deleted_at IS NULL'),
    )
    op.create_unique_constraint('clusters_name_key', 'clusters', ['name'])
    op.drop_column('clusters', 'compute_provider')
