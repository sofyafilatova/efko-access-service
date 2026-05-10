from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from uuid import UUID, uuid4
from datetime import date, time, datetime, timedelta
from typing import Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.models.shift import ShiftAssignment
from app.models.employee import EmployeeView
from app.models.shift_template import ShiftTemplate
from app.models.notification import Notification

router = APIRouter(prefix="/web/schedules", tags=["Web - Schedules"])


@router.get("/templates")
def get_shift_templates(
    db: Session = Depends(get_db),
):
    templates = db.query(ShiftTemplate).filter(ShiftTemplate.is_active == True).all()
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "code": t.code,
            "planned_start": t.planned_start.strftime("%H:%M"),
            "planned_end": t.planned_end.strftime("%H:%M"),
            "work_days_pattern": t.work_days_pattern,
            "is_active": t.is_active
        }
        for t in templates
    ]


@router.get("/staff-stats")
def get_staff_stats(
    db: Session = Depends(get_db),
):
    query = text("""
        SELECT 
            COUNT(CASE WHEN l.type = 'office' OR l.name ILIKE '%офис%' THEN 1 END) as office_count,
            COUNT(CASE WHEN l.type IN ('factory', 'production') OR l.name ILIKE '%завод%' OR l.name ILIKE '%проходная%' THEN 1 END) as factory_count,
            COUNT(*) as total
        FROM employees_view e
        LEFT JOIN workstations_view w ON e.workstation_id = w.id
        LEFT JOIN locations_view l ON w.location_id = l.id
        WHERE e.status = 'active'
    """)
    result = db.execute(query).fetchone()
    
    return {
        "office_count": result[0] or 0,
        "factory_count": result[1] or 0,
        "total": result[2] or 0
    }


@router.get("/weekly-stats")
def get_weekly_stats(
    start_date: date = Query(..., description="Понедельник недели (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    end_date = start_date + timedelta(days=7)
    
    query = text("""
        SELECT 
            COALESCE(SUM(EXTRACT(EPOCH FROM (planned_end - planned_start))/3600), 0) as total_hours,
            COUNT(*) as total_shifts,
            COUNT(CASE WHEN EXTRACT(HOUR FROM planned_start) BETWEEN 6 AND 17 THEN 1 END) as day_shifts,
            COUNT(CASE WHEN EXTRACT(HOUR FROM planned_start) >= 18 
                        OR EXTRACT(HOUR FROM planned_start) < 6 THEN 1 END) as night_shifts
        FROM shift_assignments
        WHERE shift_date >= :start_date AND shift_date < :end_date
    """)
    result = db.execute(query, {"start_date": start_date, "end_date": end_date}).fetchone()
    
    return {
        "start_date": start_date.isoformat(),
        "end_date": (end_date - timedelta(days=1)).isoformat(),
        "total_hours": round(result[0] or 0, 1),
        "total_shifts": result[1] or 0,
        "day_shifts": result[2] or 0,
        "night_shifts": result[3] or 0
    }


@router.get("/employee-calendar")
def get_employee_calendar(
    employee_id: UUID = Query(...),
    year: int = Query(2026),
    month: int = Query(5),
    db: Session = Depends(get_db),
):
    employee = db.query(EmployeeView).filter(EmployeeView.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)
    
    shifts = db.query(ShiftAssignment).filter(
        ShiftAssignment.employee_id == employee_id,
        ShiftAssignment.shift_date >= start_date,
        ShiftAssignment.shift_date < end_date
    ).order_by(ShiftAssignment.shift_date).all()
    
    calendar = []
    for day in range(1, 32):
        try:
            current_date = date(year, month, day)
        except ValueError:
            break
        
        day_shifts = [s for s in shifts if s.shift_date == current_date]
        
        calendar.append({
            "date": current_date.isoformat(),
            "day_of_week": current_date.strftime("%A"),
            "shifts": [
                {
                    "id": str(s.id),
                    "planned_start": s.planned_start.strftime("%H:%M"),
                    "planned_end": s.planned_end.strftime("%H:%M"),
                    "status": s.status,
                    "shift_template_id": str(s.shift_template_id) if s.shift_template_id else None
                }
                for s in day_shifts
            ]
        })
    
    return {
        "employee_id": str(employee_id),
        "employee_name": employee.full_name,
        "year": year,
        "month": month,
        "calendar": calendar
    }


class AddShiftRequest(BaseModel):
    employee_id: UUID
    shift_template_id: UUID
    shift_date: date
    comment: Optional[str] = None


@router.post("/add-shift")
def add_shift_to_employee(
    data: AddShiftRequest,
    db: Session = Depends(get_db),
):
    template = db.query(ShiftTemplate).filter(ShiftTemplate.id == data.shift_template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Shift template not found")
    
    # Получаем информацию о сотруднике
    employee = db.query(EmployeeView).filter(EmployeeView.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    existing = db.query(ShiftAssignment).filter(
        ShiftAssignment.employee_id == data.employee_id,
        ShiftAssignment.shift_date == data.shift_date
    ).first()
    
    if existing:
        raise HTTPException(status_code=409, detail="Shift already exists for this employee on this date")
    
    new_shift = ShiftAssignment(
        id=uuid4(),
        employee_id=data.employee_id,
        shift_template_id=data.shift_template_id,
        shift_date=data.shift_date,
        planned_start=datetime.combine(data.shift_date, template.planned_start),
        planned_end=datetime.combine(data.shift_date, template.planned_end),
        status="scheduled"
    )
    db.add(new_shift)
    
    # Создаём уведомление
    notification_body = f"Вам добавлена смена: {template.name} ({template.planned_start.strftime('%H:%M')} — {template.planned_end.strftime('%H:%M')}) на {data.shift_date}"
    if data.comment:
        notification_body += f"\nКомментарий: {data.comment}"
    
    notification = Notification(
        id=uuid4(),
        employee_id=data.employee_id,
        title="📅 Новая смена",
        body=notification_body,
        category="schedule_change",
        is_read=False,
        created_at=datetime.utcnow()
    )
    db.add(notification)
    
    db.commit()
    db.refresh(new_shift)
    
    return {
        "message": "Shift added successfully",
        "shift_id": str(new_shift.id),
        "employee_id": str(data.employee_id),
        "shift_date": data.shift_date.isoformat(),
        "planned_start": new_shift.planned_start.isoformat(),
        "planned_end": new_shift.planned_end.isoformat(),
        "status": new_shift.status
    }


class DeleteShiftRequest(BaseModel):
    reason: Optional[str] = None


@router.delete("/shift/{shift_id}")
def delete_shift(
    shift_id: UUID,
    reason: Optional[str] = Query(None, description="Причина удаления"),
    db: Session = Depends(get_db),
):
    shift = db.query(ShiftAssignment).filter(ShiftAssignment.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    
    # Получаем информацию о сотруднике
    employee = db.query(EmployeeView).filter(EmployeeView.id == shift.employee_id).first()
    
    # Сохраняем дату для уведомления
    shift_date = shift.shift_date
    
    # Удаляем смену
    db.delete(shift)
    
    # Создаём уведомление
    if employee:
        notification_body = f"Смена на {shift_date} отменена"
        if reason:
            notification_body += f"\nПричина: {reason}"
        
        notification = Notification(
            id=uuid4(),
            employee_id=shift.employee_id,
            title="❌ Смена отменена",
            body=notification_body,
            category="schedule_change",
            is_read=False,
            created_at=datetime.utcnow()
        )
        db.add(notification)
    
    db.commit()
    
    return {"message": "Shift deleted successfully"}


@router.get("/employees")
def get_active_employees(
    db: Session = Depends(get_db),
):
    employees = db.query(EmployeeView).filter(EmployeeView.status == 'active').order_by(EmployeeView.full_name).all()
    return [
        {
            "id": str(e.id),
            "full_name": e.full_name,
            "personnel_number": e.personnel_number
        }
        for e in employees
    ]