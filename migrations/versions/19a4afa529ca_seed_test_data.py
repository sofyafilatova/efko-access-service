"""seed_test_data

Revision ID: 19a4afa529ca
Revises: 1eb60ff2d910
Create Date: 2026-04-30 03:56:40.051249

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '19a4afa529ca'
down_revision: Union[str, None] = '1eb60ff2d910'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    import uuid
    from datetime import datetime, date

    # Отдел
    dept_id = str(uuid.uuid4())
    op.execute(f"""
        INSERT INTO departments_view (id, name, code, type)
        VALUES ('{dept_id}', 'Производство масличных культур', 'PROD-OIL', 'division')
    """)

    # Должность
    pos_id = str(uuid.uuid4())
    op.execute(f"""
        INSERT INTO positions_view (id, title, code, department_id)
        VALUES ('{pos_id}', 'Старший инженер', 'SR-ENG', '{dept_id}')
    """)

    # Сотрудник с тем же ID что в dev-токене
    emp_id = '00000000-0000-0000-0000-000000000001'
    op.execute(f"""
        INSERT INTO employees_view
            (id, personnel_number, full_name, department_id, position_id, status, hire_date)
        VALUES
            ('{emp_id}', 'EMP-00001', 'Иванов Иван Иванович',
             '{dept_id}', '{pos_id}', 'active', '2022-03-01')
    """)

    # Профиль
    op.execute(f"""
        INSERT INTO employee_profiles
            (employee_id, last_name, first_name, patronymic, phone)
        VALUES
            ('{emp_id}', 'Иванов', 'Иван', 'Иванович', '+7-900-000-0001')
    """)


def downgrade() -> None:
    op.execute("DELETE FROM employee_profiles WHERE employee_id = '00000000-0000-0000-0000-000000000001'")
    op.execute("DELETE FROM employees_view WHERE id = '00000000-0000-0000-0000-000000000001'")
    op.execute("DELETE FROM positions_view WHERE code = 'SR-ENG'")
    op.execute("DELETE FROM departments_view WHERE code = 'PROD-OIL'") 

