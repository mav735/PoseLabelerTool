"""image shard

Revision ID: 0003_image_shard
Revises: 0002_per_dataset
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_image_shard"
down_revision = "0002_per_dataset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default fills existing rows; flat datasets are correctly "".
    op.add_column("images", sa.Column("shard", sa.String(8), nullable=False,
                                      server_default=""))
    # Drop the server default so new rows must supply the value explicitly,
    # matching the model, which has only a Python-side default.
    op.alter_column("images", "shard", server_default=None)


def downgrade() -> None:
    op.drop_column("images", "shard")
