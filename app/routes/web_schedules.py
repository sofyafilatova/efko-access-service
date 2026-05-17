from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from uuid import UUID, uuid4
from datetime import date, time, datetime, timedelta
from typing import Optional, List
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
    
    existing = db.query(ShiftAssignment).filter(
        ShiftAssignment.employee_id == data.employee_id,
        ShiftAssignment.shift_date == data.shift_date
    ).first()
    
    if existing:
        raise HTTPException(status_code=409, detail="Shift already exists for this employee on this date")
    
    start_datetime = datetime.combine(data.shift_date, template.planned_start)
    end_datetime = datetime.combine(data.shift_date, template.planned_end)
    
    new_shift = ShiftAssignment(
        id=uuid4(),
        employee_id=data.employee_id,
        shift_template_id=data.shift_template_id,
        shift_date=data.shift_date,
        planned_start=start_datetime,
        planned_end=end_datetime,
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
    
    db.query(ShiftAssignment).filter(
        ShiftAssignment.employee_id == data.employee_id,
        ShiftAssignment.shift_date >= data.start_date,
        ShiftAssignment.shift_date <= data.end_date
    ).delete()
    
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
    
    db.query(ShiftAssignment).filter(
        ShiftAssignment.employee_id == data.employee_id,
        ShiftAssignment.shift_date >= data.start_date,
        ShiftAssignment.shift_date <= data.end_date
    ).delete()
    
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


class DayOffRequest(BaseModel):
    employee_id: UUID
    date: date
    reason: Optional[str] = None


@router.post("/send-day-off")
def send_day_off_notification(
    data: DayOffRequest,
    db: Session = Depends(get_db),
):
    employee = db.query(EmployeeView).filter(EmployeeView.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    existing_shift = db.query(ShiftAssignment).filter(
        ShiftAssignment.employee_id == data.employee_id,
        ShiftAssignment.shift_date == data.date
    ).first()
    
    if existing_shift:
        db.delete(existing_shift)
    
    day_off_template = db.query(ShiftTemplate).filter(ShiftTemplate.code == 'DAY_OFF').first()
    if not day_off_template:
        day_off_template = ShiftTemplate(
            id=uuid4(),
            name="Отгул",
            code="DAY_OFF",
            planned_start=datetime.strptime("00:00", "%H:%M").time(),
            planned_end=datetime.strptime("00:00", "%H:%M").time(),
            work_days_pattern="0000000",
            is_active=True
        )
        db.add(day_off_template)
        db.commit()
        db.refresh(day_off_template)
    
    day_off_shift = ShiftAssignment(
        id=uuid4(),
        employee_id=data.employee_id,
        shift_template_id=day_off_template.id,
        shift_date=data.date,
        planned_start=datetime.combine(data.date, day_off_template.planned_start),
        planned_end=datetime.combine(data.date, day_off_template.planned_end),
        status="day_off"
    )
    db.add(day_off_shift)
    
    notification_body = f"Оформлен отгул на {data.date}"
    if data.reason:
        notification_body += f"\nПричина: {data.reason}"
    
    notification = Notification(
        id=uuid4(),
        employee_id=data.employee_id,
        title="🎯 Отгул оформлен",
        body=notification_body,
        category="day_off",
        is_read=False,
        created_at=datetime.utcnow()
    )
    db.add(notification)
    
    db.commit()
    
    return {
        "message": "Day off notification sent successfully",
        "date": data.date.isoformat()
    }


class MarkMissedRequest(BaseModel):
    shift_id: UUID
    reason: Optional[str] = None


@router.post("/mark-missed")
def mark_shift_as_missed(
    data: MarkMissedRequest,
    db: Session = Depends(get_db),
):
    shift = db.query(ShiftAssignment).filter(ShiftAssignment.id == data.shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    
    employee = db.query(EmployeeView).filter(EmployeeView.id == shift.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    old_status = shift.status
    shift.status = "missed"
    db.commit()
    
    notification_body = f"Смена на {shift.shift_date} отмечена как прогул"
    if data.reason:
        notification_body += f"\nПричина: {data.reason}"
    
    notification = Notification(
        id=uuid4(),
        employee_id=shift.employee_id,
        title="⚠️ Смена отмечена как прогул",
        body=notification_body,
        category="schedule_change",
        is_read=False,
        created_at=datetime.utcnow()
    )
    db.add(notification)
    db.commit()
    
    return {
        "message": f"Shift marked as missed (was: {old_status})",
        "shift_id": str(shift.id),
        "shift_date": shift.shift_date.isoformat(),
        "status": shift.status
    }


class RemindShiftRequest(BaseModel):
    shift_id: UUID
    comment: Optional[str] = None


@router.post("/remind-shift")
def remind_about_shift(
    data: RemindShiftRequest,
    db: Session = Depends(get_db),
):
    shift = db.query(ShiftAssignment).filter(ShiftAssignment.id == data.shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    
    employee = db.query(EmployeeView).filter(EmployeeView.id == shift.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    template = db.query(ShiftTemplate).filter(ShiftTemplate.id == shift.shift_template_id).first()
    
    if template:
        time_str = f"{template.planned_start.strftime('%H:%M')} — {template.planned_end.strftime('%H:%M')}"
    else:
        time_str = f"{shift.planned_start.strftime('%H:%M')} — {shift.planned_end.strftime('%H:%M')}"
    
    notification_body = f"Напоминание: у вас запланирована смена на {shift.shift_date} ({time_str})"
    if data.comment:
        notification_body += f"\nКомментарий: {data.comment}"
    
    notification = Notification(
        id=uuid4(),
        employee_id=shift.employee_id,
        title="🔔 Напоминание о смене",
        body=notification_body,
        category="reminder",
        is_read=False,
        created_at=datetime.utcnow()
    )
    db.add(notification)
    db.commit()
    
    return {
        "message": "Reminder sent successfully",
        "shift_id": str(shift.id),
        "employee_id": str(shift.employee_id),
        "shift_date": shift.shift_date.isoformat()
    }


# =====================================================
# АВТОМАТИЧЕСКОЕ НАЗНАЧЕНИЕ СМЕН (ИСПРАВЛЕННАЯ ВЕРСИЯ)
# =====================================================

class AutoAssignRequest(BaseModel):
    year: int
    month: int
    override_existing: bool = True


@router.post("/auto-assign")
def auto_assign_shifts(
    data: AutoAssignRequest,
    db: Session = Depends(get_db),
):
    """Автоматическое назначение смен на месяц для всех активных сотрудников"""
    
    templates = db.query(ShiftTemplate).filter(ShiftTemplate.is_active == True).all()
    office_templates = [t for t in templates if t.code.startswith('OFFICE')]
    factory_templates = [t for t in templates if t.code.startswith('FACTORY')]
    
    employees = db.query(EmployeeView).filter(EmployeeView.status == 'active').all()
    
    office_employees = []
    factory_employees = []
    
    for emp in employees:
        is_office = False
        if emp.workstation_id:
            query = text("""
                SELECT l.type 
                FROM workstations_view w
                LEFT JOIN locations_view l ON w.location_id = l.id
                WHERE w.id = :workstation_id
            """)
            result = db.execute(query, {"workstation_id": emp.workstation_id}).fetchone()
            if result and result[0] == 'office':
                is_office = True
        
        if is_office:
            office_employees.append(emp)
        else:
            factory_employees.append(emp)
    
    office_shifts_created = 0
    for emp in office_employees:
        shifts = generate_office_shifts(emp, data.year, data.month, office_templates)
        office_shifts_created += save_shifts(emp.id, shifts, data.override_existing, db)
    
    factory_shifts_created = 0
    for emp in factory_employees:
        shifts = generate_factory_shifts_fixed(emp, data.year, data.month, factory_templates)
        factory_shifts_created += save_shifts(emp.id, shifts, data.override_existing, db)
    
    return {
        "message": "Автоназначение завершено",
        "office_employees": len(office_employees),
        "factory_employees": len(factory_employees),
        "office_shifts_created": office_shifts_created,
        "factory_shifts_created": factory_shifts_created,
        "total_shifts": office_shifts_created + factory_shifts_created
    }


def generate_office_shifts(employee: EmployeeView, year: int, month: int, templates: List[ShiftTemplate]) -> List[dict]:
    """Офисные сотрудники: 5/2, только рабочие дни (пн-пт), одна смена в день"""
    
    shifts = []
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)
    
    office_template = next((t for t in templates if t.code == 'OFFICE-STD'), templates[0] if templates else None)
    if not office_template:
        return shifts
    
    current_date = start_date
    while current_date < end_date:
        # Только будние дни (пн=0 ... пт=4)
        if current_date.weekday() < 5:
            shifts.append({
                "shift_date": current_date,
                "planned_start": datetime.combine(current_date, office_template.planned_start),
                "planned_end": datetime.combine(current_date, office_template.planned_end),
                "shift_template_id": office_template.id,
                "status": "scheduled"
            })
        current_date += timedelta(days=1)
    
    return shifts


def generate_factory_shifts_fixed(employee: EmployeeView, year: int, month: int, templates: List[ShiftTemplate]) -> List[dict]:
    """
    Заводские сотрудники: график 2/2 (2 дня работы, 2 дня отдыха)
    Смены чередуются по кругу: MORNING → DAY → EVENING → NIGHT → MORNING...
    """
    
    shifts = []
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)
    
    # Шаблоны смен в правильном порядке
    template_order = ['FACTORY-MORNING', 'FACTORY-DAY', 'FACTORY-EVENING', 'FACTORY-NIGHT']
    factory_templates = []
    for code in template_order:
        t = next((t for t in templates if t.code == code), None)
        if t:
            factory_templates.append(t)
    
    if not factory_templates:
        return shifts
    
    # Определяем стартовую позицию в ротации на основе ID сотрудника
    start_index = abs(hash(employee.id)) % len(factory_templates)
    
    current_date = start_date
    day_in_cycle = 0  # 0,1 - работа, 2,3 - отдых
    template_index = start_index
    
    while current_date < end_date:
        # Дни работы: 0 и 1 в цикле
        if day_in_cycle < 2:
            template = factory_templates[template_index % len(factory_templates)]
            
            current_start = datetime.combine(current_date, template.planned_start)
            
            # Если смена ночная (заканчивается на следующий день)
            if template.planned_end >= template.planned_start:
                current_end = datetime.combine(current_date, template.planned_end)
            else:
                current_end = datetime.combine(current_date + timedelta(days=1), template.planned_end)
            
            shifts.append({
                "shift_date": current_date,
                "planned_start": current_start,
                "planned_end": current_end,
                "shift_template_id": template.id,
                "status": "scheduled"
            })
            
            # После каждого рабочего дня меняем тип смены
            template_index += 1
        
        current_date += timedelta(days=1)
        day_in_cycle = (day_in_cycle + 1) % 4
    
    return shifts


def save_shifts(employee_id: UUID, new_shifts: List[dict], override_existing: bool, db: Session) -> int:
    """Сохраняет смены в БД"""
    
    shifts_created = 0
    
    for shift_data in new_shifts:
        shift_date = shift_data["shift_date"]
        
        if override_existing:
            db.query(ShiftAssignment).filter(
                ShiftAssignment.employee_id == employee_id,
                ShiftAssignment.shift_date == shift_date
            ).delete()
        
        existing = db.query(ShiftAssignment).filter(
            ShiftAssignment.employee_id == employee_id,
            ShiftAssignment.shift_date == shift_date
        ).first()
        
        if not existing:
            new_shift = ShiftAssignment(
                id=uuid4(),
                employee_id=employee_id,
                shift_template_id=shift_data["shift_template_id"],
                shift_date=shift_data["shift_date"],
                planned_start=shift_data["planned_start"],
                planned_end=shift_data["planned_end"],
                status=shift_data["status"]
            )
            db.add(new_shift)
            shifts_created += 1
    
    db.commit()
    return shifts_created


@router.get("/tk-validator/{employee_id}")
def validate_tk_rf(
    employee_id: UUID,
    year: int = Query(..., description="Год"),
    month: int = Query(..., description="Месяц (1-12)"),
    db: Session = Depends(get_db),
):
    employee = db.query(EmployeeView).filter(EmployeeView.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)
    
    # Получаем смены за месяц
    month_shifts = db.query(ShiftAssignment).filter(
        ShiftAssignment.employee_id == employee_id,
        ShiftAssignment.shift_date >= start_date,
        ShiftAssignment.shift_date <= end_date,
        ShiftAssignment.status.in_(['scheduled', 'in_progress', 'completed'])
    ).order_by(ShiftAssignment.shift_date, ShiftAssignment.planned_start).all()
    
    if not month_shifts:
        return {
            "employee_id": str(employee_id),
            "employee_name": employee.full_name,
            "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            "checks": {},
            "overall_ok": True,
            "message": "Нет смен за выбранный период"
        }
    
    # =========================================================
    # 1. Межсменный отдых
    # =========================================================
    min_rest = 999
    for i in range(1, len(month_shifts)):
        prev_end = month_shifts[i-1].planned_end
        curr_start = month_shifts[i].planned_start
        rest_hours = (curr_start - prev_end).total_seconds() / 3600
        if rest_hours < min_rest:
            min_rest = rest_hours
    
    if min_rest == 999:
        min_rest = None
        rest_ok = True
    else:
        min_rest = round(min_rest, 1)
        rest_ok = min_rest >= 12
    
    # =========================================================
    # 2. Недельная нагрузка
    # =========================================================
    weekly_hours = {}
    for shift in month_shifts:
        week_num = shift.shift_date.isocalendar()[1]
        year_num = shift.shift_date.year
        key = f"{year_num}-{week_num}"
        hours = (shift.planned_end - shift.planned_start).total_seconds() / 3600
        weekly_hours[key] = weekly_hours.get(key, 0) + hours
    
    max_weekly = max(weekly_hours.values()) if weekly_hours else 0
    weekly_hours_ok = max_weekly <= 40
    
    # =========================================================
    # 3. Еженедельный отдых
    # =========================================================
    weeks = {}
    for shift in month_shifts:
        week_num = shift.shift_date.isocalendar()[1]
        week_year = shift.shift_date.year
        key = f"{week_year}-{week_num}"
        if key not in weeks:
            weeks[key] = []
        weeks[key].append(shift)
    
    sorted_weeks = sorted(weeks.keys())
    
    weekly_rest_values = []
    for i in range(len(sorted_weeks) - 1):
        current_week = sorted_weeks[i]
        next_week = sorted_weeks[i + 1]
        
        last_shift = max(weeks[current_week], key=lambda x: x.planned_end)
        first_shift = min(weeks[next_week], key=lambda x: x.planned_start)
        
        rest_hours = (first_shift.planned_start - last_shift.planned_end).total_seconds() / 3600
        weekly_rest_values.append(round(rest_hours, 1))
    
    if weekly_rest_values:
        min_weekly_rest = min(weekly_rest_values)
        weekly_rest_ok = min_weekly_rest >= 42
    else:
        min_weekly_rest = None
        weekly_rest_ok = True
    
    # =========================================================
    # 4. Сверхурочные
    # =========================================================
    overtime_total = 0
    for hours in weekly_hours.values():
        if hours > 40:
            overtime_total += hours - 40
    overtime_ok = overtime_total <= 120
    
    # =========================================================
    # 5. Ночные смены
    # =========================================================
    night_shifts = 0
    for shift in month_shifts:
        start_hour = shift.planned_start.hour
        if start_hour >= 22 or start_hour < 6:
            night_shifts += 1
    
    # =========================================================
    # 6. Норма за месяц
    # =========================================================
    work_days = 0
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            work_days += 1
        current += timedelta(days=1)
    
    month_norm = work_days * 8
    total_hours = sum((s.planned_end - s.planned_start).total_seconds() / 3600 for s in month_shifts)
    month_ok = total_hours <= month_norm
    
    overall_ok = rest_ok and weekly_hours_ok and weekly_rest_ok and overtime_ok and month_ok
    
    return {
        "employee_id": str(employee_id),
        "employee_name": employee.full_name,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "checks": {
            "rest_between_shifts": {
                "value": min_rest,
                "required": "≥ 12 часов",
                "is_ok": rest_ok,
                "message": f"Межсменный отдых: {min_rest} ч" if min_rest else "Нет данных"
            },
            "weekly_rest": {
                "value": min_weekly_rest,
                "required": "≥ 42 часов",
                "is_ok": weekly_rest_ok,
                "message": f"Еженедельный отдых: {min_weekly_rest} ч" if min_weekly_rest else "Нет данных"
            },
            "weekly_hours": {
                "value": round(max_weekly, 1),
                "required": "≤ 40 часов",
                "is_ok": weekly_hours_ok,
                "message": f"Макс. часов в неделю: {round(max_weekly, 1)}"
            },
            "overtime": {
                "value": round(overtime_total, 1),
                "required": "≤ 120 часов/год",
                "is_ok": overtime_ok,
                "message": f"Сверхурочные: {round(overtime_total, 1)}"
            },
            "night_shifts": {
                "value": night_shifts,
                "required": "",
                "is_ok": True,
                "message": f"Ночных смен: {night_shifts}"
            },
            "month_hours": {
                "value": round(total_hours, 1),
                "required": f"≤ {month_norm} часов",
                "is_ok": month_ok,
                "message": f"Отработано: {round(total_hours, 1)} / {month_norm} ч"
            }
        },
        "overall_ok": overall_ok
    }