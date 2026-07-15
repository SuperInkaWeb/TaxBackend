"""add_tickets

Revision ID: a9c4e7d21f85
Revises: f6c2d8a41b73
Create Date: 2026-07-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a9c4e7d21f85'
down_revision: Union[str, None] = 'f6c2d8a41b73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tickets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asunto', sa.String(length=200), nullable=False),
        sa.Column('status', sa.Enum('abierto', 'respondido', 'cerrado', name='ticketstatus'), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tickets_id'), 'tickets', ['id'])
    op.create_index(op.f('ix_tickets_status'), 'tickets', ['status'])
    op.create_index(op.f('ix_tickets_company_id'), 'tickets', ['company_id'])

    op.create_table(
        'ticket_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('mensaje', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id']),
        sa.ForeignKeyConstraint(['author_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ticket_messages_id'), 'ticket_messages', ['id'])
    op.create_index(op.f('ix_ticket_messages_ticket_id'), 'ticket_messages', ['ticket_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_ticket_messages_ticket_id'), table_name='ticket_messages')
    op.drop_index(op.f('ix_ticket_messages_id'), table_name='ticket_messages')
    op.drop_table('ticket_messages')
    op.drop_index(op.f('ix_tickets_company_id'), table_name='tickets')
    op.drop_index(op.f('ix_tickets_status'), table_name='tickets')
    op.drop_index(op.f('ix_tickets_id'), table_name='tickets')
    op.drop_table('tickets')
    sa.Enum(name='ticketstatus').drop(op.get_bind(), checkfirst=True)
