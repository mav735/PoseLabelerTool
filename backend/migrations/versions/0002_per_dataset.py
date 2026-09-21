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
        # `table` is interpolated into the SQL text directly, which would be a
        # SQL-injection risk if it ever came from user input. It is safe here
        # only because it is always one of the literal strings in the
        # module-level _TABLES tuple above, never a caller-supplied value. If
        # a future migration needs to build this from anything less fixed,
        # quote it properly (e.g. sa.table(table) / quoted_name) instead of
        # copying this f-string.
        op.execute(sa.text(f"UPDATE {table} SET dataset = :d").bindparams(d=default))
        op.alter_column(table, "dataset", nullable=False)

    # add_column does not emit the index an index=True column carries in the
    # ORM (only create_table does), so these two must be issued by hand.
    # Names match what SQLAlchemy generates for Review.dataset / DedupPair.dataset.
    op.create_index("ix_reviews_dataset", "reviews", ["dataset"])
    op.create_index("ix_dedup_pairs_dataset", "dedup_pairs", ["dataset"])

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
    op.drop_index("ix_dedup_pairs_dataset", table_name="dedup_pairs")
    op.drop_index("ix_reviews_dataset", table_name="reviews")
    for table in _TABLES:
        op.drop_column(table, "dataset")
