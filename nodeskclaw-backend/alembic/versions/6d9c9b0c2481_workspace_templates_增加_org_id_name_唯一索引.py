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
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE workspace_templates AS t
        SET name = t.name || ' (' || LEFT(t.id::text, 6) || ')'
        WHERE t.deleted_at IS NULL
          AND EXISTS (
              SELECT 1 FROM workspace_templates AS t2
              WHERE t2.org_id IS NOT DISTINCT FROM t.org_id
                AND t2.name = t.name
                AND t2.deleted_at IS NULL
                AND t2.created_at > t.created_at
          )
    """))
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
