"""add instance_llm_overrides table

Revision ID: c8d4e1f2a3b5
Revises: b7d2e9f31a04
Create Date: 2026-03-27 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c8d4e1f2a3b5'
down_revision: Union[str, Sequence[str], None] = 'b7d2e9f31a04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'instance_llm_overrides',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('instance_id', sa.String(36), nullable=False, index=True),
        sa.Column('provider', sa.String(32), nullable=False),
        sa.Column('base_url', sa.String(512), nullable=True),
        sa.Column('api_type', sa.String(32), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['instance_id'], ['instances.id']),
    )
    op.create_index(
        'ix_instance_llm_overrides_deleted_at',
        'instance_llm_overrides',
        ['deleted_at'],
    )
    op.create_index(
        'uq_instance_llm_overrides_inst_provider',
        'instance_llm_overrides',
        ['instance_id', 'provider'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_instance_llm_overrides_inst_provider', table_name='instance_llm_overrides')
    op.drop_index('ix_instance_llm_overrides_deleted_at', table_name='instance_llm_overrides')
    op.drop_table('instance_llm_overrides')
