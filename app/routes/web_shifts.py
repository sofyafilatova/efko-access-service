from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.core.database import get_db
from app.models.employee import EmployeeView, LocationView, PositionView
from app.models.shift import ShiftAssignment
from datetime import datetime, date

router = APIRouter(prefix="/web/shifts", tags=["Web - Shifts"])

@router.get("/by-date")
def get_shifts_by_date(
    shift_date: str = Query(..., description="Дата в формате YYYY-MM-DD"),
    location_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """
    Список сотрудников со сменами на указанную дату.
    Для веб-панели (мониторинг смен).
    """
    target_date = datetime.strptime(shift_date, "%Y-%m-%d").date()
    
    # Запрос смен с JOIN на сотрудников, локации, должности
    shifts = (
        db.query(
            ShiftAssignment,
            EmployeeView.full_name,
            EmployeeView.personnel_number,
            EmployeeView.status.label("employee_status"),
            LocationView.name.label("location_name"),
            PositionView.title.label("position_title"),
        )
        .join(EmployeeView, ShiftAssignment.employee_id == EmployeeView.id)
        .outerjoin(LocationView, EmployeeView.location_id == LocationView.id)
        .outerjoin(PositionView, EmployeeView.position_id == PositionView.id)
        .filter(ShiftAssignment.shift_date == target_date)
        .all()
    )
    
    # Фильтр по локации (офису)
    if location_id:
        shifts = [s for s in shifts if s[0].employee.location_id == location_id]
    
    result = []
    for shift, full_name, personnel_number, emp_status, location_name, position_title in shifts:
        planned_start = shift.planned_start.strftime("%H:%M")
        planned_end = shift.planned_end.strftime("%H:%M")
        
        # Статус смены для отображения
        shift_status_map = {
            "scheduled": "⏳ Запланирована",
            "in_progress": "🟢 В процессе",
            "completed": "✅ Завершена",
            "missed": "❌ Прогул",
            "overtime": "⚡ Переработка",
            "sick_leave": "🟡 Больничный",
            "vacation": "🎯 Отпуск",
        }
        shift_status_display = shift_status_map.get(shift.status, shift.status)
        
        # Эффективность (примерная логика)
        efficiency = None
        if shift.status == "completed":
            # Если смена завершена и была прогул? — нет, это completed
            efficiency = "100%"
        elif shift.status == "in_progress":
            efficiency = "В процессе"
        elif shift.status == "missed":
            efficiency = "0%"
        elif shift.status == "overtime":
            efficiency = "переработка"
        else:
            efficiency = "—"
        
        result.append({
            "employee_id": str(shift.employee_id),
            "personnel_number": personnel_number,
            "full_name": full_name,
            "location": location_name or "—",
            "position": position_title or "—",
            "shift_status": shift_status_display,
            "shift_time": f"{planned_start} — {planned_end}",
            "efficiency": efficiency,
            "employee_status": "Активен" if emp_status == "active" else "Заблокирован",
        })
    
    return {"date": shift_date, "items": result, "total": len(result)}