from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db
from app.models.employee import EmployeeView, LocationView, PositionView, WorkstationView
from app.models.shift import ShiftAssignment
from datetime import datetime, timedelta

router = APIRouter(prefix="/web/shifts", tags=["Web - Shifts"])

@router.get("/by-date")
def get_shifts_by_date(
    shift_date: str = Query(..., description="Дата в формате YYYY-MM-DD"),
    location_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Список сотрудников со сменами на указанную дату.
    Используем прямой SQL для получения актуальных статусов с учётом времени.
    """
    target_date = datetime.strptime(shift_date, "%Y-%m-%d").date()
    
    # Используем SQL с CASE для динамического определения статуса
    query = text("""
        WITH shift_status_updated AS (
            SELECT 
                s.id,
                s.employee_id,
                s.shift_date,
                s.planned_start,
                s.planned_end,
                s.status as original_status,
                s.shift_template_id,
                CASE 
                    -- Если статус уже vacation/sick_leave/day_off - не меняем
                    WHEN s.status IN ('vacation', 'sick_leave', 'day_off') THEN s.status
                    -- Если planned_end <= NOW() - смена завершена
                    WHEN s.planned_end <= NOW() THEN 'completed'
                    -- Если planned_start <= NOW() AND planned_end > NOW() - смена в процессе
                    WHEN s.planned_start <= NOW() AND s.planned_end > NOW() THEN 'in_progress'
                    ELSE s.status
                END as current_status
            FROM shift_assignments s
            WHERE s.shift_date = :target_date
        )
        SELECT 
            s.employee_id,
            e.personnel_number,
            e.full_name,
            l.name as location_name,
            p.title as position_title,
            s.current_status as shift_status,
            TO_CHAR(s.planned_start, 'HH24:MI') || ' — ' || TO_CHAR(s.planned_end, 'HH24:MI') as shift_time,
            CASE 
                WHEN s.current_status = 'completed' THEN '100%'
                WHEN s.current_status = 'in_progress' THEN 'В процессе'
                ELSE '—'
            END as efficiency,
            CASE 
                WHEN e.status = 'active' THEN 'Активен'
                ELSE 'Заблокирован'
            END as employee_status
        FROM shift_status_updated s
        JOIN employees_view e ON s.employee_id = e.id
        LEFT JOIN workstations_view w ON e.workstation_id = w.id
        LEFT JOIN locations_view l ON w.location_id = l.id
        LEFT JOIN positions_view p ON e.position_id = p.id
        WHERE (:location_id IS NULL OR l.id = :location_id)
        ORDER BY s.planned_start
    """)
    
    result = db.execute(query, {"target_date": target_date, "location_id": location_id})
    rows = result.fetchall()
    
    shift_status_map = {
        "scheduled": "⏳ Запланирована",
        "in_progress": "🟢 В процессе",
        "completed": "✅ Завершена",
        "missed": "❌ Прогул",
        "overtime": "⚡ Переработка",
        "sick_leave": "🟡 Больничный",
        "vacation": "🎯 Отпуск",
        "day_off": "🎯 Отгул",
    }
    
    items = []
    for row in rows:
        status = row[5]
        status_display = shift_status_map.get(status, status)
        
        items.append({
            "employee_id": str(row[0]),
            "personnel_number": row[1],
            "full_name": row[2],
            "location": row[3] or "—",
            "position": row[4] or "—",
            "shift_status": status_display,
            "shift_time": row[6],
            "efficiency": row[7],
            "employee_status": row[8]
        })
    
    return {"date": shift_date, "items": items, "total": len(items)}