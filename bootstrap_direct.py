"""
Bootstrap: заливает данные из ядра EFKO в нашу БД.
Запуск: python bootstrap_direct.py
"""
import requests
import psycopg2
import uuid
from datetime import datetime, date
import time

KERNEL_URL = "https://microkernel-kmpo.duckdns.org/api"
EMAIL    = "manager.mzh@efko.local"
PASSWORD = "Efko2024!"

DATABASE_URL = "postgresql://postgres:ymCTYuoHanxBUnnlkaZRTJHzEZGyTpSH@switchyard.proxy.rlwy.net:36316/railway?sslmode=require"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print(f"✅ DATABASE_URL: {DATABASE_URL[:40]}...")

def get_conn(retries=3):
    for i in range(retries):
        try:
            return psycopg2.connect(DATABASE_URL)
        except Exception as e:
            print(f"   ⚠️ Попытка {i+1} подключения failed: {e}")
            if i < retries - 1:
                time.sleep(2)
            else:
                raise

def get_token():
    print(f"\n🔑 Авторизуемся как {EMAIL}...")
    r = requests.post(f"{KERNEL_URL}/auth/login",
        json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    r.raise_for_status()
    token = r.json().get("accessToken")
    print("   ✅ Токен получен")
    return token

def fetch_all(token, path):
    """Загружает все данные одним запросом"""
    r = requests.get(f"{KERNEL_URL}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30)
    if not r.ok:
        print(f"   ⚠️  {path}: {r.status_code}")
        return []
    data = r.json()
    if isinstance(data, list):
        return data
    # Пробуем извлечь данные из разных ключей
    for key in ("locations", "employees", "departments", "positions", 
                "productionLines", "workstations", "data", "items"):
        if key in data:
            return data[key]
    return []

def upsert_all(token):
    conn = get_conn()
    cur  = conn.cursor()
    now  = datetime.utcnow()

    # 1. Локации
    locations = fetch_all(token, "/personnel/locations")
    print(f"\n💾 Локации: {len(locations)}")
    for loc in locations:
        lid = loc.get("id")
        if not lid: continue
        cur.execute("""
            INSERT INTO locations_view (id, name, code, type, country, region, city,
                 postal_code, street_address, source_system_id, synced_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
                name=EXCLUDED.name, synced_at=EXCLUDED.synced_at
        """, (lid, loc.get("name",""), loc.get("code", str(lid)[:8]),
              loc.get("type"), loc.get("country"), loc.get("region"),
              loc.get("city"), loc.get("postalCode") or loc.get("postal_code"),
              loc.get("streetAddress") or loc.get("street_address"),
              loc.get("sourceSystemId") or loc.get("source_system_id"), now))
    conn.commit()
    print(f"   ✅ Локаций: {len(locations)}")

    # 2. Производственные линии
    prod_lines = fetch_all(token, "/personnel/production-lines")
    print(f"💾 Производственные линии: {len(prod_lines)}")
    for pl in prod_lines:
        plid = pl.get("id")
        if not plid: continue
        cur.execute("""
            INSERT INTO production_lines_view (id, name, code, location_id, description,
                 capacity, is_active, source_system_id, synced_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name
        """, (plid, pl.get("name",""), pl.get("code", str(plid)[:8]),
              pl.get("locationId") or pl.get("location_id"), pl.get("description"),
              pl.get("capacity"), pl.get("isActive", True),
              pl.get("sourceSystemId"), now))
    conn.commit()
    print(f"   ✅ Линий: {len(prod_lines)}")

    # 3. Рабочие станции
    workstations = fetch_all(token, "/personnel/workstations")
    print(f"💾 Рабочие станции: {len(workstations)}")
    for ws in workstations:
        wsid = ws.get("id")
        if not wsid: continue
        cur.execute("""
            INSERT INTO workstations_view (id, name, code, location_id, production_line_id,
                 workstation_type, source_system_id, synced_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name
        """, (wsid, ws.get("name",""), ws.get("code", str(wsid)[:8]),
              ws.get("locationId") or ws.get("location_id"),
              ws.get("productionLineId") or ws.get("production_line_id"),
              ws.get("workstationType") or ws.get("workstation_type"),
              ws.get("sourceSystemId"), now))
    conn.commit()
    print(f"   ✅ Станций: {len(workstations)}")

    # 4. Подразделения
    depts = fetch_all(token, "/personnel/departments")
    print(f"💾 Подразделения: {len(depts)}")
    for d in depts:
        did = d.get("id")
        if not did: continue
        cur.execute("""
            INSERT INTO departments_view (id, name, code, type, parent_id, head_employee_id)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name
        """, (did, d.get("name",""), d.get("code", str(did)[:8]),
              (d.get("type") or "department").lower(),
              d.get("parentId") or d.get("parent_id"),
              d.get("headEmployeeId") or d.get("head_employee_id")))
    conn.commit()
    print(f"   ✅ Отделов: {len(depts)}")

    # 5. Должности
    positions = fetch_all(token, "/personnel/positions")
    print(f"💾 Должности: {len(positions)}")
    for p in positions:
        pid = p.get("id")
        if not pid: continue
        cur.execute("""
            INSERT INTO positions_view (id, title, code, department_id)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title
        """, (pid, p.get("title",""), p.get("code", str(pid)[:8]),
              p.get("departmentId") or p.get("department_id")))
    conn.commit()
    print(f"   ✅ Должностей: {len(positions)}")

    # 6. Сотрудники
    employees = fetch_all(token, "/personnel/employees")
    print(f"💾 Сотрудники: {len(employees)}")
    ok = 0
    for e in employees:
        eid = e.get("id")
        name = e.get("fullName") or e.get("full_name","")
        if not eid or not name: continue
        pnum = e.get("personnelNumber") or e.get("personnel_number") or f"EMP-{str(eid)[:6]}"
        dept = e.get("departmentId") or e.get("department_id")
        pos = e.get("positionId") or e.get("position_id")
        loc = e.get("locationId") or e.get("location_id")
        ws = e.get("workstationId") or e.get("workstation_id")
        
        # Проверяем, существует ли должность
        if pos:
            cur.execute("SELECT 1 FROM positions_view WHERE id = %s", (pos,))
            if not cur.fetchone():
                pos = None
        
        status = (e.get("status") or "ACTIVE").lower()
        etype = (e.get("employmentType") or e.get("employment_type") or "MAIN").lower()
        hire = e.get("hireDate") or e.get("hire_date")
        term = e.get("terminationDate") or e.get("termination_date")
        dob = e.get("dateOfBirth") or e.get("date_of_birth")

        cur.execute("""
            INSERT INTO employees_view
                (id, personnel_number, full_name, department_id, position_id,
                 location_id, workstation_id, status, employment_type,
                 hire_date, termination_date, date_of_birth, synced_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
                full_name=EXCLUDED.full_name,
                position_id=EXCLUDED.position_id,
                synced_at=EXCLUDED.synced_at
        """, (eid, pnum, name, dept, pos, loc, ws,
              status, etype, hire, term, dob, now))

        # Профиль
        parts = name.split()
        cur.execute("""
            INSERT INTO employee_profiles (employee_id, last_name, first_name, patronymic)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (employee_id) DO UPDATE SET
                last_name=EXCLUDED.last_name, first_name=EXCLUDED.first_name
        """, (eid, parts[0] if len(parts)>0 else "",
              parts[1] if len(parts)>1 else "",
              parts[2] if len(parts)>2 else ""))
        ok += 1

    conn.commit()
    print(f"   ✅ Сотрудников: {ok}")

    # Тестовые смены на сегодня
    today = date.today()
    for e in employees[:10]:
        eid = e.get("id")
        if not eid: continue
        cur.execute("""
            INSERT INTO shift_assignments
                (id, employee_id, shift_date, planned_start, planned_end, status)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (employee_id, shift_date) DO NOTHING
        """, (str(uuid.uuid4()), eid, today,
              datetime.combine(today, datetime.strptime("09:00","%H:%M").time()),
              datetime.combine(today, datetime.strptime("18:00","%H:%M").time()),
              "in_progress"))
    conn.commit()
    print(f"   ✅ Тестовых смен добавлено: {len(employees[:10])}")
    cur.close()
    conn.close()

if __name__ == "__main__":
    print("="*55)
    print("  Bootstrap → Railway БД")
    print("="*55)
    token = get_token()
    upsert_all(token)
    print("\n✅ Готово!")