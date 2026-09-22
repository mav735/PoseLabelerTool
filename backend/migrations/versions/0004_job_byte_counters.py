"""job byte counters

Revision ID: 0004_job_byte_counters
Revises: 0003_image_shard
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_job_byte_counters"
down_revision = "0003_image_shard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # jobs.processed/total used to count IMAGES (tens of thousands); the HF
    # transport plan repurposed them to count BYTES. A 32-bit INTEGER tops
    # out at ~2.0 GiB, and the acceptance repo alone is 2.62 GB, so the first
    # progress write on a real download overflowed it. Existing rows hold
    # small values either way, so this widening needs no data migration.
    op.alter_column("jobs", "processed", type_=sa.BigInteger())
    op.alter_column("jobs", "total", type_=sa.BigInteger())


def downgrade() -> None:
    # Fails on any row already holding a value above 2**31-1 -- correct and
    # honest: there is no way to represent that value back in an INTEGER.
    op.alter_column("jobs", "processed", type_=sa.Integer())
    op.alter_column("jobs", "total", type_=sa.Integer())
