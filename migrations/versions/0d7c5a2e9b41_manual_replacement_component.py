"""Temporary manual replacement component for maintenance validation.

Revision ID: 0d7c5a2e9b41
Revises: 651707a52d7f
"""
from alembic import op
import sqlalchemy as sa

revision = "0d7c5a2e9b41"
down_revision = "651707a52d7f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ordem_servico_item", sa.Column("peca_manual", sa.String(180), nullable=True))


def downgrade():
    op.drop_column("ordem_servico_item", "peca_manual")
