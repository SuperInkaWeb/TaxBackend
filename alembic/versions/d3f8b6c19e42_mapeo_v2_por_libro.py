"""mapeo_v2_por_libro

Revision ID: d3f8b6c19e42
Revises: c7a9e2b45d18
Create Date: 2026-07-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd3f8b6c19e42'
down_revision: Union[str, None] = 'c7a9e2b45d18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('company_file_mappings', sa.Column('tipo_libro', sa.String(length=10), nullable=False, server_default='ventas'))
    op.add_column('company_file_mappings', sa.Column('columnas', sa.JSON(), nullable=True))
    op.add_column('company_file_mappings', sa.Column('serie_numero_combinado', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.drop_constraint('company_file_mappings_company_id_key', 'company_file_mappings', type_='unique')
    op.create_unique_constraint(
        'uq_file_mapping_company_libro', 'company_file_mappings', ['company_id', 'tipo_libro']
    )


def downgrade() -> None:
    op.drop_constraint('uq_file_mapping_company_libro', 'company_file_mappings', type_='unique')
    op.create_unique_constraint('company_file_mappings_company_id_key', 'company_file_mappings', ['company_id'])
    op.drop_column('company_file_mappings', 'serie_numero_combinado')
    op.drop_column('company_file_mappings', 'columnas')
    op.drop_column('company_file_mappings', 'tipo_libro')
