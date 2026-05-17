from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import UUID

from app.core.database import get_db

router = APIRouter(prefix="/web/reports", tags=["Web - Reports"])


@router.get("/attendance-summary")
def get_attendance_summary(
    start_date: date = Query(...),
    end_date: date = Query(...),
    location_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
):
    """Сводка по посещаемости за период (raw SQL)"""
    
    # Фильтр по локации
    location_filter = ""
    location_param = {}
    if location_id:
        location_filter = "AND l.id = :location_id"
        location_param = {"location_id": location_id}
    
    # Общая статистика
    stats_query = text(f"""
        SELECT 
            COUNT(DISTINCT e.id) as total_employees,
            COALESCE(SUM(
                CASE WHEN s.status = 'completed' THEN 
                    EXTRACT(EPOCH FROM (s.planned_end - s.planned_start))/3600 
                ELSE 0 END
            ), 0) as total_hours,
            COUNT(CASE WHEN s.status = 'missed' THEN 1 END) as total_missed,
            COUNT(CASE WHEN s.status = 'sick_leave' THEN 1 END) as total_sick,
            COUNT(CASE WHEN s.status = 'vacation' THEN 1 END) as total_vacation,
            COUNT(CASE WHEN EXTRACT(HOUR FROM s.planned_start) BETWEEN 6 AND 17 THEN 1 END) as day_shifts,
            COUNT(CASE WHEN EXTRACT(HOUR FROM s.planned_start) >= 18 OR EXTRACT(HOUR FROM s.planned_start) < 6 THEN 1 END) as night_shifts
        FROM shift_assignments s
        JOIN employees_view e ON s.employee_id = e.id
        LEFT JOIN workstations_view w ON e.workstation_id = w.id
        LEFT JOIN locations_view l ON w.location_id = l.id
        WHERE s.shift_date >= :start_date 
        AND s.shift_date <= :end_date
        {location_filter}
    """)
    
    params = {"start_date": start_date, "end_date": end_date, **location_param}
    result = db.execute(stats_query, params).fetchone()
    
    # Ежедневные данные
    daily_query = text(f"""
        SELECT 
            s.shift_date,
            COALESCE(SUM(EXTRACT(EPOCH FROM (s.planned_end - s.planned_start))/3600), 0) as hours,
            COUNT(*) as shifts_count
        FROM shift_assignments s
        JOIN employees_view e ON s.employee_id = e.id
        LEFT JOIN workstations_view w ON e.workstation_id = w.id
        LEFT JOIN locations_view l ON w.location_id = l.id
        WHERE s.shift_date >= :start_date 
        AND s.shift_date <= :end_date
        AND s.status = 'completed'
        {location_filter}
        GROUP BY s.shift_date
        ORDER BY s.shift_date
    """)
    
    daily = db.execute(daily_query, params).fetchall()
    
    daily_data = []
    for d in daily:
        daily_data.append({
            "date": d[0].isoformat(),
            "hours": round(d[1] or 0, 1),
            "shifts_count": d[2]
        })
    
    # По дням недели
    weekday_query = text(f"""
        SELECT 
            EXTRACT(DOW FROM s.shift_date) as dow,
            COALESCE(SUM(EXTRACT(EPOCH FROM (s.planned_end - s.planned_start))/3600), 0) as hours
        FROM shift_assignments s
        JOIN employees_view e ON s.employee_id = e.id
        LEFT JOIN workstations_view w ON e.workstation_id = w.id
        LEFT JOIN locations_view l ON w.location_id = l.id
        WHERE s.shift_date >= :start_date 
        AND s.shift_date <= :end_date
        AND s.status = 'completed'
        {location_filter}
        GROUP BY EXTRACT(DOW FROM s.shift_date)
        ORDER BY dow
    """)
    
    weekday_result = db.execute(weekday_query, params).fetchall()
    weekday_map = {int(r[0]): round(r[1] or 0, 1) for r in weekday_result}
    weekday_labels = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
    weekday_hours = [weekday_map.get(i, 0) for i in range(1, 8)]
    
    return {
        "total_employees": result[0] or 0,
        "total_hours": round(result[1] or 0, 1),
        "total_shifts": sum(d[2] for d in daily),
        "total_missed": result[2] or 0,
        "total_sick_leave": result[3] or 0,
        "total_vacation": result[4] or 0,
        "day_shifts": result[5] or 0,
        "night_shifts": result[6] or 0,
        "daily_data": daily_data,
        "weekday_hours": weekday_hours,
        "weekday_labels": weekday_labels,
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
    """Отпуска и больничные за месяц (raw SQL)"""
    
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)
    
    query = text("""
        SELECT 
            e.full_name,
            s.status,
            s.shift_date
        FROM shift_assignments s
        JOIN employees_view e ON s.employee_id = e.id
        WHERE s.shift_date >= :start_date 
        AND s.shift_date <= :end_date
        AND s.status IN ('vacation', 'sick_leave')
        ORDER BY e.full_name, s.shift_date
    """)
    
    rows = db.execute(query, {"start_date": start_date, "end_date": end_date}).fetchall()
    
    # Группировка по сотрудникам
    leaves_by_employee = {}
    for row in rows:
        name = row[0]
        status = row[1]
        shift_date = row[2]
        
        if name not in leaves_by_employee:
            leaves_by_employee[name] = {
                "type": status,
                "start_date": shift_date,
                "end_date": shift_date,
                "days": 1
            }
        else:
            if shift_date < leaves_by_employee[name]["start_date"]:
                leaves_by_employee[name]["start_date"] = shift_date
            if shift_date > leaves_by_employee[name]["end_date"]:
                leaves_by_employee[name]["end_date"] = shift_date
            leaves_by_employee[name]["days"] += 1
    
    leaves_list = []
    for name, data in leaves_by_employee.items():
        if leave_type == "all" or data["type"] == leave_type:
            leaves_list.append({
                "name": name,
                "type": data["type"],
                "start_date": data["start_date"].isoformat(),
                "end_date": data["end_date"].isoformat(),
                "days": data["days"]
            })
    
    # Календарь
    days_in_month = (end_date - start_date).days + 1
    calendar = []
    for day in range(1, days_in_month + 1):
        current_date = date(year, month, day)
        day_leaves = [l for l in leaves_list if current_date >= date.fromisoformat(l["start_date"]) and current_date <= date.fromisoformat(l["end_date"])]
        calendar.append({
            "day": day,
            "has_leave": len(day_leaves) > 0,
            "leave_count": len(day_leaves)
        })
    
    return {
        "total_employees": len(leaves_list),
        "total_days": sum(l["days"] for l in leaves_list),
        "vacation_count": len([l for l in leaves_list if l["type"] == "vacation"]),
        "sick_leave_count": len([l for l in leaves_list if l["type"] == "sick_leave"]),
        "leaves": leaves_list,
        "calendar": calendar
    }


@router.get("/shift-analytics")
def get_shift_analytics(
    year: int = Query(...),
    month: int = Query(...),
    db: Session = Depends(get_db),
):
    """Аналитика смен за месяц с правильным расчётом сверхурочных (по сотрудникам и неделям)"""
    
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)
    
    # Получаем все ЗАВЕРШЁННЫЕ смены за месяц с employee_id
    query = text("""
        SELECT 
            s.employee_id,
            EXTRACT(HOUR FROM s.planned_start) as start_hour,
            EXTRACT(EPOCH FROM (s.planned_end - s.planned_start))/3600 as hours,
            s.shift_date
        FROM shift_assignments s
        WHERE s.shift_date >= :start_date 
        AND s.shift_date <= :end_date
        AND s.status = 'completed'
    """)
    
    rows = db.execute(query, {"start_date": start_date, "end_date": end_date}).fetchall()
    
    day_shifts = 0
    night_shifts = 0
    total_hours = 0
    total_shifts = len(rows)
    shift_types = {"morning": 0, "day": 0, "evening": 0, "night": 0}
    
    # Группируем часы по сотрудникам и неделям для расчёта сверхурочных
    employee_weekly_hours = {}  # {employee_id: {week_key: hours}}
    
    for row in rows:
        employee_id = row[0]
        start_hour = row[1] or 0
        hours = row[2] or 0
        shift_date = row[3]
        
        if hours < 0:
            hours += 24
        
        total_hours += hours
        
        # Типы смен по времени начала
        if 6 <= start_hour < 10:
            shift_types["morning"] += 1
        elif 10 <= start_hour < 14:
            shift_types["day"] += 1
        elif 14 <= start_hour < 22:
            shift_types["evening"] += 1
        else:
            shift_types["night"] += 1
        
        # Дневные/ночные смены
        if 6 <= start_hour <= 17:
            day_shifts += 1
        else:
            night_shifts += 1
        
        # Для сверхурочных: группируем по сотрудникам и неделям
        week_num = shift_date.isocalendar()[1]
        week_key = f"{shift_date.year}-{week_num}"
        
        if employee_id not in employee_weekly_hours:
            employee_weekly_hours[employee_id] = {}
        
        employee_weekly_hours[employee_id][week_key] = employee_weekly_hours[employee_id].get(week_key, 0) + hours
    
    # Расчёт сверхурочных: суммируем часы сверх 40 за каждую неделю для каждого сотрудника
    overtime = 0
    for employee_id, weeks in employee_weekly_hours.items():
        for week_key, week_hours in weeks.items():
            if week_hours > 40:
                overtime += week_hours - 40
    
    return {
        "day_shifts": day_shifts,
        "night_shifts": night_shifts,
        "total_shifts": total_shifts,
        "total_hours": round(total_hours, 1),
        "overtime": round(overtime, 1),
        "shift_types": shift_types
    }