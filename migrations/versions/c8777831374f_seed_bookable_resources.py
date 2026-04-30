"""seed_bookable_resources

Revision ID: c8777831374f
Revises: 1b201f13db64
Create Date: 2026-04-30 04:59:48.482921

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8777831374f'
down_revision: Union[str, None] = '1b201f13db64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    import uuid

    # Берём зону которую уже создавали
    op.execute("""
        INSERT INTO bookable_resources (id, label, type, zone_id, floor, capacity, is_active)
        SELECT
            gen_random_uuid(),
            'Рабочее место №1',
            'workplace',
            id,
            1,
            1,
            true
        FROM zones WHERE code = 'MAIN-GATE'
        LIMIT 1
    """)

    op.execute("""
        INSERT INTO bookable_resources (id, label, type, zone_id, floor, capacity, is_active)
        SELECT
            gen_random_uuid(),
            'Переговорная Альфа',
            'meeting_room',
            id,
            2,
            8,
            true
        FROM zones WHERE code = 'MAIN-GATE'
        LIMIT 1
    """)


def downgrade() -> None:
    op.execute("DELETE FROM bookable_resources WHERE label IN ('Рабочее место №1', 'Переговорная Альфа')")