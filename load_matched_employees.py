import json
import psycopg2
from datetime import datetime

DATABASE_URL = "postgresql://postgres:ymCTYuoHanxBUnnlkaZRTJHzEZGyTpSH@switchyard.proxy.rlwy.net:36316/railway?sslmode=require"

def load_employees_with_existing_positions():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    now = datetime.utcnow()

    with open("employees.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        employees = data.get("employees") or data.get("data") or []

    print(f"📥 Проверяю {len(employees)} сотрудников...")

    total_loaded = 0
    total_skipped = 0

    for emp in employees:
        eid = emp.get("id")
        name = emp.get("fullName") or emp.get("full_name")
        if not eid or not name:
            continue

        # Получаем position_id
        pos_id = emp.get("positionId") or emp.get("position_id")
        
        # Если нет position_id — пропускаем
        if not pos_id:
            print(f"   ⚠️ Пропускаем {name}: нет position_id")
            total_skipped += 1
            continue
        
        # Проверяем, есть ли должность в БД
        cur.execute("SELECT 1 FROM positions_view WHERE id = %s", (pos_id,))
        if not cur.fetchone():
            print(f"   ⚠️ Пропускаем {name}: должность {pos_id} не найдена")
            total_skipped += 1
            continue

        # Все поля (как в твоей таблице)
        pnum = emp.get("personnelNumber") or emp.get("personnel_number") or f"EMP-{str(eid)[:6]}"
        dept_id = emp.get("departmentId") or emp.get("department_id")
        loc_id = emp.get("locationId") or emp.get("location_id")
        ws_id = emp.get("workstationId") or emp.get("workstation_id")
        source_event_id = emp.get("sourceEventId") or emp.get("source_event_id")
        
        status = (emp.get("status") or "ACTIVE").lower()
        etype = (emp.get("employmentType") or emp.get("employment_type") or "MAIN").lower()
        hire = emp.get("hireDate") or emp.get("hire_date")
        term = emp.get("terminationDate") or emp.get("termination_date")
        dob = emp.get("dateOfBirth") or emp.get("date_of_birth")

        cur.execute("""
            INSERT INTO employees_view
                (id, personnel_number, full_name, department_id, position_id,
                 location_id, workstation_id, source_event_id,
                 status, employment_type, hire_date, termination_date, date_of_birth, synced_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
                full_name = EXCLUDED.full_name,
                location_id = EXCLUDED.location_id,
                workstation_id = EXCLUDED.workstation_id,
                source_event_id = EXCLUDED.source_event_id,
                synced_at = EXCLUDED.synced_at
        """, (eid, pnum, name, dept_id, pos_id, loc_id, ws_id, source_event_id,
              status, etype, hire, term, dob, now))

        total_loaded += 1
        if total_loaded % 200 == 0:
            conn.commit()
            print(f"   ✅ Загружено {total_loaded} сотрудников...")

    conn.commit()
    print(f"\n✅ ГОТОВО! Загружено: {total_loaded}, Пропущено: {total_skipped}")
    cur.close()
    conn.close()

if __name__ == "__main__":
    load_employees_with_existing_positions()