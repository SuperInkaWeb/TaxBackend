"""add_propuesta_origen

Revision ID: c7a9e2b45d18
Revises: b8d4f1a72c93
Create Date: 2026-07-09 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7a9e2b45d18'
down_revision: Union[str, None] = 'b8d4f1a72c93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reconciliation_jobs', sa.Column('propuesta_origen_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('reconciliation_jobs', 'propuesta_origen_at')
