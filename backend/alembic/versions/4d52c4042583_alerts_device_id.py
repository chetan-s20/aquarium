"""alerts.device_id (device-offline alerts)

Revision ID: 4d52c4042583
Revises: 5dbbc50ec3ec
Create Date: 2026-11-19 17:18:11.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d52c4042583'
down_revision: Union[str, None] = '5dbbc50ec3ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('alerts', sa.Column('device_id', sa.String(length=36), nullable=True))
    op.create_index(op.f('ix_alerts_device_id'), 'alerts', ['device_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_alerts_device_id'), table_name='alerts')
    op.drop_column('alerts', 'device_id')
