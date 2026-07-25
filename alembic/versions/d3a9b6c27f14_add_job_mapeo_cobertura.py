"""add mapeo_config y cobertura_fechas a reconciliation_jobs

Revision ID: d3a9b6c27f14
Revises: c2f8a4d15e60
Create Date: 2026-07-24 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd3a9b6c27f14'
down_revision: Union[str, None] = 'c2f8a4d15e60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reconciliation_jobs', sa.Column('mapeo_config', sa.JSON(), nullable=True))
    op.add_column('reconciliation_jobs', sa.Column('cobertura_fechas', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('reconciliation_jobs', 'cobertura_fechas')
    op.drop_column('reconciliation_jobs', 'mapeo_config')
