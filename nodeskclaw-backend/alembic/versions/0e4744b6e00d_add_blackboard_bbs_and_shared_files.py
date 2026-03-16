"""add_blackboard_bbs_and_shared_files

Revision ID: 0e4744b6e00d
Revises: e4f3e8e640ce
Create Date: 2026-03-16 16:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0e4744b6e00d'
down_revision: str | Sequence[str] | None = 'e4f3e8e640ce'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # -- blackboard_posts --
    op.create_table('blackboard_posts',
    sa.Column('workspace_id', sa.String(length=36), nullable=False),
    sa.Column('title', sa.String(length=256), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('author_type', sa.String(length=10), nullable=False),
    sa.Column('author_id', sa.String(length=36), nullable=False),
    sa.Column('author_name', sa.String(length=128), nullable=False),
    sa.Column('is_pinned', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    sa.Column('reply_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
    sa.Column('last_reply_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_blackboard_posts_workspace_id'), 'blackboard_posts', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_blackboard_posts_author_id'), 'blackboard_posts', ['author_id'], unique=False)
    op.create_index(op.f('ix_blackboard_posts_deleted_at'), 'blackboard_posts', ['deleted_at'], unique=False)
    op.create_index('ix_blackboard_posts_ws_active', 'blackboard_posts',
        ['workspace_id', 'is_pinned', 'last_reply_at'],
        postgresql_where=sa.text('deleted_at IS NULL'))

    # -- blackboard_replies --
    op.create_table('blackboard_replies',
    sa.Column('post_id', sa.String(length=36), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('author_type', sa.String(length=10), nullable=False),
    sa.Column('author_id', sa.String(length=36), nullable=False),
    sa.Column('author_name', sa.String(length=128), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['post_id'], ['blackboard_posts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_blackboard_replies_post_id'), 'blackboard_replies', ['post_id'], unique=False)
    op.create_index(op.f('ix_blackboard_replies_deleted_at'), 'blackboard_replies', ['deleted_at'], unique=False)

    # -- post_reads --
    op.create_table('post_reads',
    sa.Column('post_id', sa.String(length=36), nullable=False),
    sa.Column('reader_type', sa.String(length=10), nullable=False),
    sa.Column('reader_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['post_id'], ['blackboard_posts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_post_reads_post_id'), 'post_reads', ['post_id'], unique=False)
    op.create_index(op.f('ix_post_reads_reader_id'), 'post_reads', ['reader_id'], unique=False)
    op.create_index(op.f('ix_post_reads_deleted_at'), 'post_reads', ['deleted_at'], unique=False)
    op.create_index('uq_post_reads_post_reader', 'post_reads',
        ['post_id', 'reader_id'], unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'))

    # -- blackboard_files --
    op.create_table('blackboard_files',
    sa.Column('workspace_id', sa.String(length=36), nullable=False),
    sa.Column('parent_path', sa.String(length=1024), nullable=False, server_default='/'),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('is_directory', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    sa.Column('file_size', sa.Integer(), nullable=False, server_default=sa.text('0')),
    sa.Column('content_type', sa.String(length=128), nullable=False, server_default=''),
    sa.Column('tos_key', sa.String(length=512), nullable=False, server_default=''),
    sa.Column('uploader_type', sa.String(length=10), nullable=False),
    sa.Column('uploader_id', sa.String(length=36), nullable=False),
    sa.Column('uploader_name', sa.String(length=128), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_blackboard_files_workspace_id'), 'blackboard_files', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_blackboard_files_deleted_at'), 'blackboard_files', ['deleted_at'], unique=False)
    op.create_index('uq_blackboard_files_ws_path_name', 'blackboard_files',
        ['workspace_id', 'parent_path', 'name'], unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_blackboard_files_ws_path_name', table_name='blackboard_files',
        postgresql_where=sa.text('deleted_at IS NULL'))
    op.drop_index(op.f('ix_blackboard_files_deleted_at'), table_name='blackboard_files')
    op.drop_index(op.f('ix_blackboard_files_workspace_id'), table_name='blackboard_files')
    op.drop_table('blackboard_files')

    op.drop_index('uq_post_reads_post_reader', table_name='post_reads',
        postgresql_where=sa.text('deleted_at IS NULL'))
    op.drop_index(op.f('ix_post_reads_deleted_at'), table_name='post_reads')
    op.drop_index(op.f('ix_post_reads_reader_id'), table_name='post_reads')
    op.drop_index(op.f('ix_post_reads_post_id'), table_name='post_reads')
    op.drop_table('post_reads')

    op.drop_index(op.f('ix_blackboard_replies_deleted_at'), table_name='blackboard_replies')
    op.drop_index(op.f('ix_blackboard_replies_post_id'), table_name='blackboard_replies')
    op.drop_table('blackboard_replies')

    op.drop_index('ix_blackboard_posts_ws_active', table_name='blackboard_posts',
        postgresql_where=sa.text('deleted_at IS NULL'))
    op.drop_index(op.f('ix_blackboard_posts_deleted_at'), table_name='blackboard_posts')
    op.drop_index(op.f('ix_blackboard_posts_author_id'), table_name='blackboard_posts')
    op.drop_index(op.f('ix_blackboard_posts_workspace_id'), table_name='blackboard_posts')
    op.drop_table('blackboard_posts')
