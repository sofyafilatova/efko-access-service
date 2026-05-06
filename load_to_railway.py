import json
import psycopg2
from datetime import datetime

DATABASE_URL = "postgresql://postgres:ymCTYuoHanxBUnnlkaZRTJHzEZGyTpSH@switchyard.proxy.rlwy.net:36316/railway?sslmode=require"

def load_employees():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    now = datetime.utcnow()

    with open("employees.json", "r", encoding="utf-8") as f:
        employees = json.load(f)

    if isinstance(employees, dict):
        if "employees" in employees:
            employees = employees["employees"]
        elif "data" in employees:
            employees = employees["data"]

    print(f"📥 Загружаю {len(employees)} сотрудников...")

    count = 0
    skipped = 0
    for emp in employees:
        eid = emp.get("id")
        name = emp.get("fullName") or emp.get("full_name")
        if not eid or not name:
            continue

        pnum = emp.get("personnelNumber") or emp.get("personnel_number") or f"EMP-{str(eid)[:6]}"
        dept = emp.get("departmentId") or emp.get("department_id")
        pos = emp.get("positionId") or emp.get("position_id")
        
        # Проверяем, существует ли должность
        if pos:
            cur.execute("SELECT 1 FROM positions_view WHERE id = %s", (pos,))
            if not cur.fetchone():
                # Если должности нет — пропускаем этого сотрудника
                print(f"   ⚠️ Пропускаем {name}: должность {pos} не найдена")
                skipped += 1
                continue
        
        status = (emp.get("status") or "ACTIVE").lower()
        etype = (emp.get("employmentType") or emp.get("employment_type") or "MAIN").lower()
        hire = emp.get("hireDate") or emp.get("hire_date")
        term = emp.get("terminationDate") or emp.get("termination_date")
        dob = emp.get("dateOfBirth") or emp.get("date_of_birth")

        try:
            cur.execute("""
                INSERT INTO employees_view
                    (id, personnel_number, full_name, department_id, position_id,
                     status, employment_type, hire_date, termination_date, date_of_birth, synced_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING
            """, (eid, pnum, name, dept, pos, status, etype, hire, term, dob, now))
            count += 1
        except Exception as e:
            print(f"   ⚠️ Ошибка при вставке {name}: {e}")
            skipped += 1

        if count % 500 == 0:
            print(f"   ✅ {count} сотрудников вставлено...")
            conn.commit()

    conn.commit()
    print(f"✅ ГОТОВО! Загружено {count} сотрудников, пропущено {skipped}")
    cur.close()
    conn.close()

if __name__ == "__main__":
    load_employees()