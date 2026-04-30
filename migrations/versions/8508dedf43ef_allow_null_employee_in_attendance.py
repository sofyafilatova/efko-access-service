"""allow_null_employee_in_attendance

Revision ID: 8508dedf43ef
Revises: c8777831374f
Create Date: 2026-04-30 05:19:28.637151

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8508dedf43ef'
down_revision: Union[str, None] = 'c8777831374f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'attendance_records',
        'employee_id',
        existing_type=sa.UUID(),
        nullable=True
    )

def downgrade() -> None:
    op.alter_column(
        'attendance_records',
        'employee_id',
        existing_type=sa.UUID(),
        nullable=False
    )