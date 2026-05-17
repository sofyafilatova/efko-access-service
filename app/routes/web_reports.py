from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import date, datetime, timedelta
from typing import Optional, List
from uuid import UUID

from app.core.database import get_db
from app.models.shift import ShiftAssignment
from app.models.employee import EmployeeView
from app.models.location import LocationView

router = APIRouter(prefix="/web/reports", tags=["Web - Reports"])


@router.get("/attendance-summary")
def get_attendance_summary(
    start_date: date = Query(...),
    end_date: date = Query(...),
    location_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
):
    """Реальная сводка по посещаемости за период"""
    
    # Базовый запрос сотрудников
    emp_query = db.query(EmployeeView).filter(EmployeeView.status == 'active')
    if location_id:
        emp_query = emp_query.filter(EmployeeView.location_id == location_id)
    employees = emp_query.all()
    total_employees = len(employees)
    
    # Запрос смен за период
    shift_query = db.query(ShiftAssignment).filter(
        ShiftAssignment.shift_date >= start_date,
        ShiftAssignment.shift_date <= end_date
    )
    
    all_shifts = shift_query.all()
    
    # Статистика по сменам
    total_hours = 0
    total_missed = 0
    total_sick_leave = 0
    total_vacation = 0
    
    day_shifts = 0
    night_shifts = 0
    
    daily_data = []
    current = start_date
    while current <= end_date:
        day_shifts_list = [s for s in all_shifts if s.shift_date == current]
        day_hours = 0
        for s in day_shifts_list:
            if s.status == 'completed':
                hours = (s.planned_end - s.planned_start).total_seconds() / 3600
                if hours < 0:
                    hours += 24
                day_hours += hours
                total_hours += hours
            elif s.status == 'missed':
                total_missed += 1
            elif s.status == 'sick_leave':
                total_sick_leave += 1
            elif s.status == 'vacation':
                total_vacation += 1
            
            # Подсчёт дневных/ночных смен
            start_hour = s.planned_start.hour
            if 6 <= start_hour <= 17:
                day_shifts += 1
            else:
                night_shifts += 1
        
        daily_data.append({
            "date": current.isoformat(),
            "hours": round(day_hours, 1),
            "shifts_count": len(day_shifts_list)
        })
        current += timedelta(days=1)
    
    # Почасовая разбивка по дням недели
    weekday_hours = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
    for shift in all_shifts:
        if shift.status == 'completed':
            hours = (shift.planned_end - shift.planned_start).total_seconds() / 3600
            if hours < 0:
                hours += 24
            weekday_hours[shift.shift_date.weekday()] += hours
    
    # Топ сотрудников по прогулам
    missed_by_employee = {}
    for shift in all_shifts:
        if shift.status == 'missed':
            missed_by_employee[shift.employee_id] = missed_by_employee.get(shift.employee_id, 0) + 1
    
    top_offenders = []
    for emp_id, count in sorted(missed_by_employee.items(), key=lambda x: x[1], reverse=True)[:5]:
        emp = db.query(EmployeeView).filter(EmployeeView.id == emp_id).first()
        if emp:
            top_offenders.append({
                "name": emp.full_name,
                "missed_count": count
            })
    
    return {
        "total_employees": total_employees,
        "total_hours": round(total_hours, 1),
        "total_shifts": len(all_shifts),
        "total_missed": total_missed,
        "total_sick_leave": total_sick_leave,
        "total_vacation": total_vacation,
        "day_shifts": day_shifts,
        "night_shifts": night_shifts,
        "daily_data": daily_data,
        "weekday_hours": [weekday_hours[i] for i in range(7)],
        "weekday_labels": ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"],
        "top_offenders": top_offenders,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "days_count": (end_date - start_date).days + 1
        }
    }


@router.get("/leave-summary")
def get_leave_summary(
    year: int = Query(...),
    month: int = Query(...),
    leave_type: Optional[str] = Query("all"),
    db: Session = Depends(get_db),
):
    """Реальные данные об отпусках и больничных"""
    
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)
    
    # Запрос смен со статусами отпуска/больничного
    status_filter = ['vacation', 'sick_leave']
    shifts = db.query(ShiftAssignment).filter(
        ShiftAssignment.shift_date >= start_date,
        ShiftAssignment.shift_date <= end_date,
        ShiftAssignment.status.in_(status_filter)
    ).all()
    
    # Группировка по сотрудникам
    employees_on_leave = {}
    for shift in shifts:
        emp_id = str(shift.employee_id)
        if emp_id not in employees_on_leave:
            emp = db.query(EmployeeView).filter(EmployeeView.id == shift.employee_id).first()
            employees_on_leave[emp_id] = {
                "name": emp.full_name if emp else "Неизвестно",
                "type": shift.status,
                "start_date": shift.shift_date,
                "end_date": shift.shift_date,
                "days": 1
            }
        else:
            if shift.shift_date < employees_on_leave[emp_id]["start_date"]:
                employees_on_leave[emp_id]["start_date"] = shift.shift_date
            if shift.shift_date > employees_on_leave[emp_id]["end_date"]:
                employees_on_leave[emp_id]["end_date"] = shift.shift_date
            employees_on_leave[emp_id]["days"] += 1
    
    leaves_list = list(employees_on_leave.values())
    
    # Фильтрация по типу
    if leave_type != "all":
        leaves_list = [l for l in leaves_list if l["type"] == leave_type]
    
    # Календарь
    days_in_month = (end_date - start_date).days + 1
    calendar = []
    for day in range(1, days_in_month + 1):
        current_date = date(year, month, day)
        day_leaves = [l for l in leaves_list if l["start_date"] <= current_date <= l["end_date"]]
        calendar.append({
            "day": day,
            "has_leave": len(day_leaves) > 0,
            "leave_count": len(day_leaves),
            "types": list(set([l["type"] for l in day_leaves]))
        })
    
    return {
        "total_employees": len(leaves_list),
        "total_days": sum(l["days"] for l in leaves_list),
        "vacation_count": len([l for l in leaves_list if l["type"] == "vacation"]),
        "sick_leave_count": len([l for l in leaves_list if l["type"] == "sick_leave"]),
        "leaves": leaves_list,
        "calendar": calendar
    }