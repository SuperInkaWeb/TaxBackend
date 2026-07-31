"""add csv_a y csv_c a report_files

Revision ID: e5b1c9d34a20
Revises: d3a9b6c27f14
Create Date: 2026-07-26 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5b1c9d34a20'
down_revision: Union[str, None] = 'd3a9b6c27f14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('report_files', sa.Column('csv_a_storage_path', sa.String(length=500), nullable=True))
    op.add_column('report_files', sa.Column('csv_a_file_size_bytes', sa.Integer(), nullable=True))
    op.add_column('report_files', sa.Column('csv_c_storage_path', sa.String(length=500), nullable=True))
    op.add_column('report_files', sa.Column('csv_c_file_size_bytes', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('report_files', 'csv_c_file_size_bytes')
    op.drop_column('report_files', 'csv_c_storage_path')
    op.drop_column('report_files', 'csv_a_file_size_bytes')
    op.drop_column('report_files', 'csv_a_storage_path')
