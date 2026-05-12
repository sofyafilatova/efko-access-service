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
    
    employee = db.query(EmployeeView).filter(EmployeeView.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Проверка существующей смены по ДАТЕ
    existing = db.query(ShiftAssignment).filter(
        ShiftAssignment.employee_id == data.employee_id,
        ShiftAssignment.shift_date == data.shift_date
    ).first()
    
    if existing:
        raise HTTPException(status_code=409, detail="Shift already exists for this employee on this date")
    
    # СОХРАНЯЕМ В ЛОКАЛЬНОМ ВРЕМЕНИ (МОСКВА)
    # planned_start и planned_end хранятся в МОСКОВСКОМ времени
    start_datetime = datetime.combine(data.shift_date, template.planned_start)
    end_datetime = datetime.combine(data.shift_date, template.planned_end)
    
    new_shift = ShiftAssignment(
        id=uuid4(),
        employee_id=data.employee_id,
        shift_template_id=data.shift_template_id,
        shift_date=data.shift_date,
        planned_start=start_datetime,  # ← теперь в локальном времени
        planned_end=end_datetime,      # ← теперь в локальном времени
        status="scheduled"
    )
    db.add(new_shift)
    
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
        "planned_start": new_shift.planned_start.strftime("%H:%M"),
        "planned_end": new_shift.planned_end.strftime("%H:%M"),
        "status": new_shift.status
    }


@router.delete("/shift/{shift_id}")
def delete_shift(
    shift_id: UUID,
    reason: Optional[str] = Query(None, description="Причина удаления"),
    db: Session = Depends(get_db),
):
    shift = db.query(ShiftAssignment).filter(ShiftAssignment.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    
    employee = db.query(EmployeeView).filter(EmployeeView.id == shift.employee_id).first()
    shift_date = shift.shift_date
    
    db.delete(shift)
    
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


@router.get("/shift-details/{shift_id}")
def get_shift_details(
    shift_id: UUID,
    db: Session = Depends(get_db),
):
    shift = db.query(ShiftAssignment).filter(ShiftAssignment.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    
    employee = db.query(EmployeeView).filter(EmployeeView.id == shift.employee_id).first()
    template = db.query(ShiftTemplate).filter(ShiftTemplate.id == shift.shift_template_id).first() if shift.shift_template_id else None
    
    notifications = db.query(Notification).filter(
        Notification.employee_id == shift.employee_id,
        Notification.category == "schedule_change"
    ).order_by(Notification.created_at.desc()).limit(5).all()
    
    return {
        "shift_id": str(shift.id),
        "employee_id": str(shift.employee_id),
        "employee_name": employee.full_name if employee else "Неизвестно",
        "shift_date": shift.shift_date.isoformat(),
        "planned_start": shift.planned_start.strftime("%H:%M"),
        "planned_end": shift.planned_end.strftime("%H:%M"),
        "status": shift.status,
        "shift_template_id": str(shift.shift_template_id) if shift.shift_template_id else None,
        "shift_template_name": template.name if template else "Индивидуальная",
        "recent_notifications": [
            {
                "id": str(n.id),
                "title": n.title,
                "body": n.body,
                "created_at": n.created_at.isoformat() if n.created_at else None
            }
            for n in notifications
        ]
    }


class VacationRequest(BaseModel):
    employee_id: UUID
    start_date: date
    end_date: date
    reason: Optional[str] = None


@router.post("/send-vacation")
def send_vacation_notification(
    data: VacationRequest,
    db: Session = Depends(get_db),
):
    employee = db.query(EmployeeView).filter(EmployeeView.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    if data.start_date > data.end_date:
        raise HTTPException(status_code=400, detail="Start date must be before end date")
    
    # Удаляем существующие смены в этот период
    db.query(ShiftAssignment).filter(
        ShiftAssignment.employee_id == data.employee_id,
        ShiftAssignment.shift_date >= data.start_date,
        ShiftAssignment.shift_date <= data.end_date
    ).delete()
    
    # Получаем или создаём шаблон для отпуска
    vacation_template = db.query(ShiftTemplate).filter(ShiftTemplate.code == 'VACATION').first()
    if not vacation_template:
        vacation_template = ShiftTemplate(
            id=uuid4(),
            name="Отпуск",
            code="VACATION",
            planned_start=datetime.strptime("00:00", "%H:%M").time(),
            planned_end=datetime.strptime("00:00", "%H:%M").time(),
            work_days_pattern="0000000",
            is_active=True
        )
        db.add(vacation_template)
        db.commit()
        db.refresh(vacation_template)
    
    # Создаём записи об отпуске (в локальном времени)
    current_date = data.start_date
    vacation_days = 0
    while current_date <= data.end_date:
        vacation_shift = ShiftAssignment(
            id=uuid4(),
            employee_id=data.employee_id,
            shift_template_id=vacation_template.id,
            shift_date=current_date,
            planned_start=datetime.combine(current_date, vacation_template.planned_start),
            planned_end=datetime.combine(current_date, vacation_template.planned_end),
            status="vacation"
        )
        db.add(vacation_shift)
        vacation_days += 1
        current_date += timedelta(days=1)
    
    # Создаём уведомление
    notification_body = f"Оформлен отпуск с {data.start_date} по {data.end_date}"
    if data.reason:
        notification_body += f"\nКомментарий: {data.reason}"
    
    notification = Notification(
        id=uuid4(),
        employee_id=data.employee_id,
        title="🏖️ Отпуск оформлен",
        body=notification_body,
        category="vacation",
        is_read=False,
        created_at=datetime.utcnow()
    )
    db.add(notification)
    
    db.commit()
    
    return {
        "message": "Vacation notification sent successfully",
        "vacation_days": vacation_days
    }


class SickLeaveRequest(BaseModel):
    employee_id: UUID
    start_date: date
    end_date: date
    reason: Optional[str] = None


@router.post("/send-sick-leave")
def send_sick_leave_notification(
    data: SickLeaveRequest,
    db: Session = Depends(get_db),
):
    employee = db.query(EmployeeView).filter(EmployeeView.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    if data.start_date > data.end_date:
        raise HTTPException(status_code=400, detail="Start date must be before end date")
    
    # Удаляем существующие смены в этот период
    db.query(ShiftAssignment).filter(
        ShiftAssignment.employee_id == data.employee_id,
        ShiftAssignment.shift_date >= data.start_date,
        ShiftAssignment.shift_date <= data.end_date
    ).delete()
    
    # Получаем или создаём шаблон для больничного
    sick_template = db.query(ShiftTemplate).filter(ShiftTemplate.code == 'SICK_LEAVE').first()
    if not sick_template:
        sick_template = ShiftTemplate(
            id=uuid4(),
            name="Больничный",
            code="SICK_LEAVE",
            planned_start=datetime.strptime("00:00", "%H:%M").time(),
            planned_end=datetime.strptime("00:00", "%H:%M").time(),
            work_days_pattern="0000000",
            is_active=True
        )
        db.add(sick_template)
        db.commit()
        db.refresh(sick_template)
    
    # Создаём записи о больничном (в локальном времени)
    current_date = data.start_date
    sick_days = 0
    while current_date <= data.end_date:
        sick_shift = ShiftAssignment(
            id=uuid4(),
            employee_id=data.employee_id,
            shift_template_id=sick_template.id,
            shift_date=current_date,
            planned_start=datetime.combine(current_date, sick_template.planned_start),
            planned_end=datetime.combine(current_date, sick_template.planned_end),
            status="sick_leave"
        )
        db.add(sick_shift)
        sick_days += 1
        current_date += timedelta(days=1)
    
    # Создаём уведомление
    notification_body = f"Оформлен больничный с {data.start_date} по {data.end_date}"
    if data.reason:
        notification_body += f"\nКомментарий: {data.reason}"
    
    notification = Notification(
        id=uuid4(),
        employee_id=data.employee_id,
        title="🩺 Больничный оформлен",
        body=notification_body,
        category="sick_leave",
        is_read=False,
        created_at=datetime.utcnow()
    )
    db.add(notification)
    
    db.commit()
    
    return {
        "message": "Sick leave notification sent successfully",
        "sick_days": sick_days
    }