"""add_operation_audit_logs

Revision ID: b3f7c1a29e04
Revises: 8a8b875bb810
Create Date: 2026-03-11 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'b3f7c1a29e04'
down_revision: Union[str, Sequence[str], None] = '8a8b875bb810'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'operation_audit_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('org_id', sa.String(length=36), nullable=True),
        sa.Column('workspace_id', sa.String(length=36), nullable=True),
        sa.Column('action', sa.String(length=255), nullable=False),
        sa.Column('target_type', sa.String(length=32), nullable=False),
        sa.Column('target_id', sa.String(length=36), nullable=False),
        sa.Column('actor_type', sa.String(length=16), nullable=False),
        sa.Column('actor_id', sa.String(length=36), nullable=False),
        sa.Column('actor_name', sa.String(length=128), nullable=True),
        sa.Column('details', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_operation_audit_logs_action'), 'operation_audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_operation_audit_logs_target_type'), 'operation_audit_logs', ['target_type'], unique=False)
    op.create_index(op.f('ix_operation_audit_logs_org_id'), 'operation_audit_logs', ['org_id'], unique=False)
    op.create_index(op.f('ix_operation_audit_logs_workspace_id'), 'operation_audit_logs', ['workspace_id'], unique=False)
    op.create_index('ix_operation_audit_logs_actor_id', 'operation_audit_logs', ['actor_id'], unique=False)
    op.create_index('ix_operation_audit_logs_created_at', 'operation_audit_logs', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_operation_audit_logs_created_at', table_name='operation_audit_logs')
    op.drop_index('ix_operation_audit_logs_actor_id', table_name='operation_audit_logs')
    op.drop_index(op.f('ix_operation_audit_logs_workspace_id'), table_name='operation_audit_logs')
    op.drop_index(op.f('ix_operation_audit_logs_org_id'), table_name='operation_audit_logs')
    op.drop_index(op.f('ix_operation_audit_logs_target_type'), table_name='operation_audit_logs')
    op.drop_index(op.f('ix_operation_audit_logs_action'), table_name='operation_audit_logs')
    op.drop_table('operation_audit_logs')
