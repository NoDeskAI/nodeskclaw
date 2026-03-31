"""workspace_template_agent_specs_and_workspace_deploys

Revision ID: f2a8c1d4e5b6
Revises: 68c9c4eb557f
Create Date: 2026-03-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


revision: str = "f2a8c1d4e5b6"
down_revision: Union[str, Sequence[str], None] = "68c9c4eb557f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspace_templates",
        sa.Column("agent_specs", JSON, nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.add_column(
        "workspace_templates",
        sa.Column("human_specs", JSON, nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.add_column("workspace_templates", sa.Column("source_workspace_id", sa.String(36), nullable=True))
    op.create_index(
        "ix_workspace_templates_source_workspace_id",
        "workspace_templates",
        ["source_workspace_id"],
    )
    op.create_foreign_key(
        "fk_workspace_templates_source_workspace_id",
        "workspace_templates",
        "workspaces",
        ["source_workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "workspace_deploys",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("workspace_id", sa.String(36), nullable=True),
        sa.Column("template_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("total_agents", sa.Integer(), nullable=False),
        sa.Column("completed_agents", sa.Integer(), nullable=False),
        sa.Column("failed_agents", sa.Integer(), nullable=False),
        sa.Column("progress_detail", JSON, nullable=False),
        sa.Column("config_snapshot", JSON, nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["workspace_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspace_deploys_workspace_id", "workspace_deploys", ["workspace_id"])
    op.create_index("ix_workspace_deploys_template_id", "workspace_deploys", ["template_id"])
    op.create_index("ix_workspace_deploys_status", "workspace_deploys", ["status"])
    op.create_index("ix_workspace_deploys_created_by", "workspace_deploys", ["created_by"])
    op.create_index("ix_workspace_deploys_org_id", "workspace_deploys", ["org_id"])
    op.create_index("ix_workspace_deploys_deleted_at", "workspace_deploys", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("workspace_deploys")
    op.drop_constraint("fk_workspace_templates_source_workspace_id", "workspace_templates", type_="foreignkey")
    op.drop_index("ix_workspace_templates_source_workspace_id", table_name="workspace_templates")
    op.drop_column("workspace_templates", "source_workspace_id")
    op.drop_column("workspace_templates", "human_specs")
    op.drop_column("workspace_templates", "agent_specs")
