"""pending changes

Revision ID: 0005_pending_changes
Revises: 0004_job_byte_counters
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_pending_changes"
down_revision = "0004_job_byte_counters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_changes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("dataset", sa.String(64), index=True, nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("op", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_index("ix_pending_changes_dataset", table_name="pending_changes")
    op.drop_table("pending_changes")
