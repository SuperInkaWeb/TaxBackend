"""add_scenario_d

Revision ID: a1f3e8c92b47
Revises: c5ddf156d46c
Create Date: 2026-07-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1f3e8c92b47'
down_revision: Union[str, None] = 'c5ddf156d46c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reconciliation_results', sa.Column('escenario_d_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('report_files', sa.Column('csv_d_storage_path', sa.String(length=500), nullable=True))
    op.add_column('report_files', sa.Column('csv_d_file_size_bytes', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('report_files', 'csv_d_file_size_bytes')
    op.drop_column('report_files', 'csv_d_storage_path')
    op.drop_column('reconciliation_results', 'escenario_d_count')
