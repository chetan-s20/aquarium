"""User login (Phase 6).

Revision ID: ea191d344f70
Revises: 4d52c4042583
Create Date: 2026-11-20 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea191d344f70'
down_revision: Union[str, None] = '4d52c4042583'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('password_hash', sa.String(length=128), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_name'), 'users', ['name'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_name'), table_name='users')
    op.drop_table('users')
