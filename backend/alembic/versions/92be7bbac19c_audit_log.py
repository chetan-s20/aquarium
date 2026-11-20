"""User login + operator-action audit log (Phase 6).

Revision ID: 92be7bbac19c
Revises: ea191d344f70
Create Date: 2026-11-20 12:52:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '92be7bbac19c'
down_revision: Union[str, None] = 'ea191d344f70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('audit_log',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('actor', sa.String(length=120), nullable=True),
        sa.Column('action', sa.String(length=40), nullable=False),
        sa.Column('entity_type', sa.String(length=40), nullable=False),
        sa.Column('entity_id', sa.String(length=36), nullable=True),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_log_action'), 'audit_log', ['action'], unique=False)
    op.create_index(op.f('ix_audit_log_actor'), 'audit_log', ['actor'], unique=False)
    op.create_index(op.f('ix_audit_log_entity_id'), 'audit_log', ['entity_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_log_entity_id'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_actor'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_action'), table_name='audit_log')
    op.drop_table('audit_log')
