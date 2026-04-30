"""seed_zones_and_credentials

Revision ID: 1b201f13db64
Revises: 19a4afa529ca
Create Date: 2026-04-30 04:21:21.931187

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b201f13db64'
down_revision: Union[str, None] = '19a4afa529ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    import uuid

    zone_id = str(uuid.uuid4())
    op.execute(f"""
        INSERT INTO zones (id, name, code, address, access_level, is_active)
        VALUES ('{zone_id}', 'Главная проходная', 'MAIN-GATE', 'Алексеевка, вход №1', 'public', true)
    """)

    point_id = str(uuid.uuid4())
    op.execute(f"""
        INSERT INTO access_points (id, name, type, zone_id, direction, is_active)
        VALUES ('{point_id}', 'Турникет №1', 'turnstile', '{zone_id}', 'both', true)
    """)

    # Credential для тестового сотрудника
    emp_id = '00000000-0000-0000-0000-000000000001'
    from datetime import datetime, timedelta
    expires = (datetime.utcnow() + timedelta(days=365)).strftime('%Y-%m-%d %H:%M:%S')
    cred_id = str(uuid.uuid4())
    op.execute(f"""
        INSERT INTO credentials (id, subject_type, subject_id, token_value, medium, issued_at, expires_at, version, is_revoked)
        VALUES ('{cred_id}', 'personal', '{emp_id}', 'TEST-TOKEN-0001', 'card', now(), '{expires}', 1, false)
    """)

    # Сохраним point_id чтобы использовать в тесте
    import builtins
    builtins._test_point_id = point_id


def downgrade() -> None:
    op.execute("DELETE FROM credentials WHERE token_value = 'TEST-TOKEN-0001'")
    op.execute("DELETE FROM access_points WHERE name = 'Турникет №1'")
    op.execute("DELETE FROM zones WHERE code = 'MAIN-GATE'")