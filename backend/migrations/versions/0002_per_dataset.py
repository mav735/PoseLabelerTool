"""per-dataset review state

Revision ID: 0002_per_dataset
Revises: 0001_baseline
"""
import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002_per_dataset"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

_TABLES = ("images", "leases", "reviews", "dedup_pairs", "jobs", "pred_cache")


def upgrade() -> None:
    default = os.environ.get("PLT_MIGRATE_DEFAULT_DATASET", "default")
    for table in _TABLES:
        op.add_column(table, sa.Column("dataset", sa.String(64), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET dataset = :d").bindparams(d=default))
        op.alter_column(table, "dataset", nullable=False)

    op.drop_constraint("images_pkey", "images", type_="primary")
    op.create_primary_key("images_pkey", "images", ["dataset", "stem"])

    op.drop_constraint("pred_cache_pkey", "pred_cache", type_="primary")
    op.create_primary_key("pred_cache_pkey", "pred_cache",
                          ["dataset", "stem", "model_key"])

    op.drop_index("uq_active_lease_stem", table_name="leases")
    op.create_index("uq_active_lease_stem", "leases", ["dataset", "stem"],
                    unique=True, postgresql_where=sa.text("released_at IS NULL"))

    op.add_column("jobs", sa.Column(
        "meta", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))


def downgrade() -> None:
    op.drop_column("jobs", "meta")
    op.drop_index("uq_active_lease_stem", table_name="leases")
    op.create_index("uq_active_lease_stem", "leases", ["stem"], unique=True,
                    postgresql_where=sa.text("released_at IS NULL"))
    op.drop_constraint("pred_cache_pkey", "pred_cache", type_="primary")
    op.create_primary_key("pred_cache_pkey", "pred_cache", ["stem", "model_key"])
    op.drop_constraint("images_pkey", "images", type_="primary")
    op.create_primary_key("images_pkey", "images", ["stem"])
    for table in _TABLES:
        op.drop_column(table, "dataset")
