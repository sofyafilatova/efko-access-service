"""
Bootstrap: заливает данные из ядра EFKO в нашу БД.
Запуск:
  python bootstrap.py email@efko.ru пароль   <- с авторизацией в ядре
  python bootstrap.py                         <- только демо-данные
"""
import requests
import psycopg2
from datetime import datetime, date
import uuid
import sys

KERNEL_URL = "https://microkernel-kmpo.duckdns.org/api"
OUR_API    = "http://localhost:8000/api"

DB_CONFIG = {
    "dbname":   "railway",
    "user":     "postgres",
    "password": r"ymCTYuoHanxBUnnlkaZRTJHzEZGyTpSH",
    "host":     "postgres.railway.internal",
    "port":     5432,
}

# ─── Авторизация ──────────────────────────────────────────────────────────────

def get_kernel_token(email: str, password: str) -> str:
    print(f"🔑 Авторизуемся в ядре как {email}...")
    r = requests.post(
        f"{KERNEL_URL}/auth/login",
        json={"email": email, "password": password},
        timeout=15
    )
    if not r.ok:
        raise Exception(f"Ошибка {r.status_code}: {r.text[:200]}")
    data = r.json()
    token = data.get("accessToken") or data.get("access_token")
    print("   ✅ Токен ядра получен")
    return token


def get_dev_token() -> str:
    r = requests.post(f"{OUR_API}/dev/token", timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]

# ─── Загрузка данных из ядра ──────────────────────────────────────────────────

def fetch_from_kernel(token: str):
    headers = {"Authorization": f"Bearer {token}"}

    print("\n📥 Загружаем подразделения...")
    r = requests.get(f"{KERNEL_URL}/personnel/departments", headers=headers, timeout=15)
    departments = []
    if r.ok:
        data = r.json()
        departments = data.get("departments", data if isinstance(data, list) else [])
        print(f"   ✅ Подразделений: {len(departments)}")
    else:
        print(f"   ⚠️  {r.status_code}: {r.text[:100]}")

    print("📥 Загружаем должности...")
    r = requests.get(f"{KERNEL_URL}/personnel/positions", headers=headers, timeout=15)
    positions = []
    if r.ok:
        data = r.json()
        positions = data.get("positions", data if isinstance(data, list) else [])
        print(f"   ✅ Должностей: {len(positions)}")
    else:
        print(f"   ⚠️  {r.status_code}: {r.text[:100]}")

    print("📥 Загружаем сотрудников...")
    r = requests.get(
        f"{KERNEL_URL}/personnel/employees",
        headers=headers,
        timeout=15
    )
    employees = []
    if r.ok:
        data = r.json()
        employees = data.get("employees", data if isinstance(data, list) else [])
        employees = [
            e for e in employees
            if (e.get("status") or "").upper() in ("ACTIVE", "")
        ]
        print(f"   ✅ Сотрудников: {len(employees)}")
    else:
        print(f"   ⚠️  {r.status_code}: {r.text[:200]}")

    print("📥 Загружаем шаблоны смен...")
    r = requests.get(f"{KERNEL_URL}/personnel/shift-templates", headers=headers, timeout=15)
    shift_templates = []
    if r.ok:
        data = r.json()
        shift_templates = data.get("templates", data if isinstance(data, list) else [])
        print(f"   ✅ Шаблонов смен: {len(shift_templates)}")
    else:
        print(f"   ⚠️  {r.status_code}: {r.text[:100]}")

    return departments, positions, employees, shift_templates

# ─── Запись в БД ──────────────────────────────────────────────────────────────

def write_to_db(departments, positions, employees):
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()
    now  = datetime.utcnow()

    # Подразделения
    dept_ok = 0
    for d in departments:
        did  = d.get("id")
        name = d.get("name", "")
        code = d.get("code", did[:8] if did else "DEPT")
        dtype    = (d.get("type") or "DEPARTMENT").lower()
        parent   = d.get("parentId") or d.get("parent_id")
        head_emp = d.get("headEmployeeId") or d.get("head_employee_id")
        if not did or not name:
            continue
        cur.execute("""
            INSERT INTO departments_view (id, name, code, type, parent_id, head_employee_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                name             = EXCLUDED.name,
                code             = EXCLUDED.code,
                type             = EXCLUDED.type,
                head_employee_id = EXCLUDED.head_employee_id
        """, (did, name, code, dtype, parent, head_emp))
        dept_ok += 1
    print(f"   💾 Подразделений записано: {dept_ok}")

    # Должности
    pos_ok = 0
    for p in positions:
        pid   = p.get("id")
        title = p.get("title", "")
        code  = p.get("code", pid[:8] if pid else "POS")
        did   = p.get("departmentId") or p.get("department_id")
        if not pid or not title:
            continue
        cur.execute("""
            INSERT INTO positions_view (id, title, code, department_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                title         = EXCLUDED.title,
                code          = EXCLUDED.code,
                department_id = EXCLUDED.department_id
        """, (pid, title, code, did))
        pos_ok += 1
    print(f"   💾 Должностей записано: {pos_ok}")

    # Сотрудники
    emp_ok = 0
    for e in employees:
        eid   = e.get("id")
        name  = e.get("fullName") or e.get("full_name", "")
        pnum  = e.get("personnelNumber") or e.get("personnel_number") or f"EMP-{str(eid)[:6]}"
        did   = e.get("departmentId") or e.get("department_id")
        pid   = e.get("positionId") or e.get("position_id")
        status = (e.get("status") or "ACTIVE").lower()
        etype  = (e.get("employmentType") or e.get("employment_type") or "MAIN").lower()
        hire   = e.get("hireDate") or e.get("hire_date")
        term   = e.get("terminationDate") or e.get("termination_date")

        if not eid or not name:
            continue

        cur.execute("""
            INSERT INTO employees_view
                (id, personnel_number, full_name, department_id, position_id,
                 status, employment_type, hire_date, termination_date, synced_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                full_name       = EXCLUDED.full_name,
                department_id   = EXCLUDED.department_id,
                position_id     = EXCLUDED.position_id,
                status          = EXCLUDED.status,
                employment_type = EXCLUDED.employment_type,
                synced_at       = EXCLUDED.synced_at
        """, (eid, pnum, name, did, pid, status, etype, hire, term, now))

        parts = name.split()
        last  = parts[0] if len(parts) > 0 else ""
        first = parts[1] if len(parts) > 1 else ""
        patr  = parts[2] if len(parts) > 2 else ""
        cur.execute("""
            INSERT INTO employee_profiles (employee_id, last_name, first_name, patronymic)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (employee_id) DO UPDATE SET
                last_name  = EXCLUDED.last_name,
                first_name = EXCLUDED.first_name,
                patronymic = EXCLUDED.patronymic
        """, (eid, last, first, patr))
        emp_ok += 1

    print(f"   💾 Сотрудников записано: {emp_ok}")
    conn.commit()
    cur.close()
    conn.close()
    return emp_ok


def add_test_shifts(employees):
    """Добавляет смены на ближайшие 7 дней для первых 10 сотрудников."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()
    today = date.today()
    count = 0

    for e in employees[:10]:
        eid = e.get("id")
        if not eid:
            continue
        cur.execute("SELECT id FROM employees_view WHERE id = %s", (eid,))
        if not cur.fetchone():
            continue

        for offset in range(7):
            d = date.fromordinal(today.toordinal() + offset)
            if d.weekday() >= 5:
                continue
            st = "in_progress" if offset == 0 else "scheduled"
            cur.execute("""
                INSERT INTO shift_assignments
                    (id, employee_id, shift_date, planned_start, planned_end, status)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (employee_id, shift_date) DO NOTHING
            """, (
                str(uuid.uuid4()), eid, d,
                datetime.combine(d, datetime.strptime("08:00", "%H:%M").time()),
                datetime.combine(d, datetime.strptime("20:00", "%H:%M").time()),
                st
            ))
        count += 1

    print(f"   💾 Смены добавлены для {count} сотрудников")
    conn.commit()
    cur.close()
    conn.close()


def add_demo_data():
    """Демо-данные если ядро недоступно."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()
    now  = datetime.utcnow()
    today = date.today()

    depts = [
        ("10000001-0000-0000-0000-000000000001", "Производство масличных культур", "PROD-OIL", "division"),
        ("10000001-0000-0000-0000-000000000002", "Дивизион пищевых ингредиентов", "FOOD-ING", "division"),
        ("10000001-0000-0000-0000-000000000003", "Логистика и склад",             "LOG-WH",   "department"),
        ("10000001-0000-0000-0000-000000000004", "ИТ и цифровые решения",         "IT-DIG",   "department"),
        ("10000001-0000-0000-0000-000000000005", "Управление персоналом",         "HR",        "department"),
    ]
    for d in depts:
        cur.execute("""
            INSERT INTO departments_view (id, name, code, type)
            VALUES (%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING
        """, d)

    positions = [
        ("20000002-0000-0000-0000-000000000001", "Старший инженер",        "SR-ENG",  depts[0][0]),
        ("20000002-0000-0000-0000-000000000002", "Оператор производства",  "OPER",    depts[0][0]),
        ("20000002-0000-0000-0000-000000000003", "Менеджер по логистике",  "LOG-MGR", depts[2][0]),
        ("20000002-0000-0000-0000-000000000004", "Разработчик",            "DEV",     depts[3][0]),
        ("20000002-0000-0000-0000-000000000005", "HR-специалист",          "HR-SPEC", depts[4][0]),
    ]
    for p in positions:
        cur.execute("""
            INSERT INTO positions_view (id, title, code, department_id)
            VALUES (%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING
        """, p)

    employees = [
        ("00000000-0000-0000-0000-000000000001", "EMP-00001", "Иванов Иван Иванович",
         depts[0][0], positions[0][0], "Иванов", "Иван", "Иванович", "+7-900-000-0001"),
        (str(uuid.uuid4()), "EMP-00002", "Петрова Анна Сергеевна",
         depts[1][0], positions[1][0], "Петрова", "Анна", "Сергеевна", "+7-900-000-0002"),
        (str(uuid.uuid4()), "EMP-00003", "Сидоров Алексей Петрович",
         depts[2][0], positions[2][0], "Сидоров", "Алексей", "Петрович", "+7-900-000-0003"),
        (str(uuid.uuid4()), "EMP-00004", "Козлова Мария Владимировна",
         depts[3][0], positions[3][0], "Козлова", "Мария", "Владимировна", "+7-900-000-0004"),
        (str(uuid.uuid4()), "EMP-00005", "Новиков Дмитрий Игоревич",
         depts[4][0], positions[4][0], "Новиков", "Дмитрий", "Игоревич", "+7-900-000-0005"),
    ]

    for eid, pnum, name, dept, pos, last, first, patr, phone in employees:
        cur.execute("""
            INSERT INTO employees_view
                (id, personnel_number, full_name, department_id, position_id, status, synced_at)
            VALUES (%s,%s,%s,%s,%s,'active',%s)
            ON CONFLICT (id) DO UPDATE SET
                full_name = EXCLUDED.full_name,
                department_id = EXCLUDED.department_id,
                synced_at = EXCLUDED.synced_at
        """, (eid, pnum, name, dept, pos, now))

        cur.execute("""
            INSERT INTO employee_profiles (employee_id, last_name, first_name, patronymic, phone)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (employee_id) DO UPDATE SET
                last_name = EXCLUDED.last_name,
                first_name = EXCLUDED.first_name,
                phone = EXCLUDED.phone
        """, (eid, last, first, patr, phone))

        for offset in range(7):
            d = date.fromordinal(today.toordinal() + offset)
            if d.weekday() >= 5:
                continue
            st = "in_progress" if offset == 0 else "scheduled"
            cur.execute("""
                INSERT INTO shift_assignments
                    (id, employee_id, shift_date, planned_start, planned_end, status)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (employee_id, shift_date) DO NOTHING
            """, (
                str(uuid.uuid4()), eid, d,
                datetime.combine(d, datetime.strptime("08:00", "%H:%M").time()),
                datetime.combine(d, datetime.strptime("20:00", "%H:%M").time()),
                st
            ))

    print(f"   💾 Демо: {len(depts)} отделов, {len(positions)} должностей, {len(employees)} сотрудников")
    conn.commit()
    cur.close()
    conn.close()

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  EFKO Access Service — Bootstrap")
    print("=" * 55)

    kernel_token = None
    use_kernel   = len(sys.argv) >= 3

    if use_kernel:
        email, password = sys.argv[1], sys.argv[2]
        try:
            kernel_token = get_kernel_token(email, password)
        except Exception as ex:
            print(f"   ❌ {ex}")
            print("   Переключаемся на демо-данные...")
            use_kernel = False

    if use_kernel and kernel_token:
        departments, positions, employees, shift_templates = fetch_from_kernel(kernel_token)
        if employees:
            print("\n💾 Записываем в БД...")
            cnt = write_to_db(departments, positions, employees)
            if cnt > 0:
                print("\n📅 Добавляем смены...")
                add_test_shifts(employees)
        else:
            print("\n⚠️  Сотрудников из ядра не получили. Добавляем демо-данные...")
            add_demo_data()
    else:
        print("\n📝 Добавляем демо-данные (ядро не используется)...")
        add_demo_data()

    print("\n✅ Bootstrap завершён!")
    print("   Откройте мобилку и обновите экраны.\n")