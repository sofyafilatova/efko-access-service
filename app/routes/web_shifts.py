from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.employee import EmployeeView, LocationView, PositionView, WorkstationView
from app.models.shift import ShiftAssignment
from datetime import datetime

router = APIRouter(prefix="/web/shifts", tags=["Web - Shifts"])

@router.get("/by-date")
def get_shifts_by_date(
    shift_date: str = Query(..., description="Дата в формате YYYY-MM-DD"),
    location_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Список сотрудников со сменами на указанную дату.
    Логика JOIN: employees_view.workstation_id → workstations_view.id → workstations_view.location_id → locations_view.id
    """
    target_date = datetime.strptime(shift_date, "%Y-%m-%d").date()
    
    query = (
        db.query(
            ShiftAssignment,
            EmployeeView.full_name,
            EmployeeView.personnel_number,
            EmployeeView.status.label("employee_status"),
            PositionView.title.label("position_title"),
            LocationView.name.label("location_name"),
        )
        .join(EmployeeView, ShiftAssignment.employee_id == EmployeeView.id)
        .outerjoin(PositionView, EmployeeView.position_id == PositionView.id)
        .outerjoin(WorkstationView, EmployeeView.workstation_id == WorkstationView.id)
        .outerjoin(LocationView, WorkstationView.location_id == LocationView.id)
        .filter(ShiftAssignment.shift_date == target_date)
    )
    
    if location_id:
        query = query.filter(LocationView.id == location_id)
    
    results = query.all()
    
    shift_status_map = {
        "scheduled": "⏳ Запланирована",
        "in_progress": "🟢 В процессе",
        "completed": "✅ Завершена",
        "missed": "❌ Прогул",
        "overtime": "⚡ Переработка",
        "sick_leave": "🟡 Больничный",
        "vacation": "🎯 Отпуск",
    }
    
    result = []
    for shift, full_name, personnel_number, emp_status, position_title, location_name in results:
        planned_start = shift.planned_start.strftime("%H:%M")
        planned_end = shift.planned_end.strftime("%H:%M")
        
        shift_status_display = shift_status_map.get(shift.status, shift.status)
        
        # Эффективность
        efficiency = "—"
        if shift.status == "completed":
            efficiency = "100%"
        elif shift.status == "in_progress":
            efficiency = "В процессе"
        elif shift.status == "missed":
            efficiency = "0%"
        elif shift.status == "overtime":
            efficiency = "переработка"
        
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