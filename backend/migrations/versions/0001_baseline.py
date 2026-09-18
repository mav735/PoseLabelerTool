"""baseline: schema as of the pose-labeler merge

Revision ID: 0001_baseline
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(64), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "images",
        sa.Column("stem", sa.String(32), primary_key=True),
        sa.Column("width", sa.Integer, default=0),
        sa.Column("height", sa.Integer, default=0),
        sa.Column("has_label", sa.Boolean, default=False),
        sa.Column("in_model_labeled", sa.Boolean, default=False),
        sa.Column("in_bad_labels", sa.Boolean, default=False),
        sa.Column("approved", sa.Boolean, default=False),
        sa.Column("deleted", sa.Boolean, default=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "leases",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("stem", sa.String(32), nullable=False),
        sa.Column("task", sa.String(16), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("leased_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("uq_active_lease_stem", "leases", ["stem"], unique=True,
                    postgresql_where=sa.text("released_at IS NULL"))
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("stem", sa.String(32), index=True, nullable=False),
        sa.Column("task", sa.String(16), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "dedup_pairs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("keeper_stem", sa.String(32), nullable=False),
        sa.Column("dup_stem", sa.String(32), index=True, nullable=False),
        sa.Column("diff", sa.Float, nullable=False),
        sa.Column("pool", sa.String(16), nullable=False),
        sa.Column("status", sa.String(8), default="todo"),
        sa.Column("action", sa.String(8), nullable=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("params", JSONB, default=dict),
        sa.Column("status", sa.String(8), default="queued"),
        sa.Column("processed", sa.Integer, default=0),
        sa.Column("total", sa.Integer, default=0),
        sa.Column("message", sa.Text, default=""),
        sa.Column("result", JSONB, default=dict),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "pred_cache",
        sa.Column("stem", sa.String(32), primary_key=True),
        sa.Column("model_key", sa.String(128), primary_key=True),
        sa.Column("preds", JSONB, default=dict),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("pred_cache")
    op.drop_table("jobs")
    op.drop_table("dedup_pairs")
    op.drop_table("reviews")
    op.drop_index("uq_active_lease_stem", table_name="leases")
    op.drop_table("leases")
    op.drop_table("images")
    op.drop_table("users")
