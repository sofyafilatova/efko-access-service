from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from app.models.shift import ShiftAssignment, AttendanceRecord, Timesheet, TimesheetEntry
from app.models.employee import EmployeeView


def get_current_shift(db: Session, employee_id: UUID) -> ShiftAssignment | None:
    now = datetime.utcnow()
    return (
        db.query(ShiftAssignment)
        .filter(
            ShiftAssignment.employee_id == employee_id,
            ShiftAssignment.planned_start <= now,
            ShiftAssignment.planned_end >= now,
        )
        .first()
    )


def get_calendar(db: Session, employee_id: UUID, year: int, month: int) -> list[dict]:
    """Смены за месяц. Без фильтра по статусу — показываем все."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)

    # Получаем ВСЕ смены за месяц без фильтра по статусу
    shifts = (
        db.query(ShiftAssignment)
        .filter(
            ShiftAssignment.employee_id == employee_id,
            ShiftAssignment.shift_date >= start,
            ShiftAssignment.shift_date <= end,
        )
        .all()
    )

    shift_map = {s.shift_date: s for s in shifts}

    result = []
    current = start
    while current <= end:
        shift = shift_map.get(current)
        result.append({
            "date": current.isoformat(),
            "has_shift": current in shift_map,
            "shift": shift,
        })
        current += timedelta(days=1)
    return result


def get_month_stats(db: Session, employee_id: UUID, year: int, month: int) -> dict:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)

    shifts = (
        db.query(ShiftAssignment)
        .filter(
            ShiftAssignment.employee_id == employee_id,
            ShiftAssignment.shift_date >= start,
            ShiftAssignment.shift_date <= end,
        )
        .all()
    )

    total = len(shifts)
    completed = sum(1 for s in shifts if s.status == "completed")
    missed = sum(1 for s in shifts if s.status == "missed")
    in_progress = sum(1 for s in shifts if s.status == "in_progress")

    planned_hours = Decimal(0)
    actual_hours = Decimal(0)

    for s in shifts:
        duration = (s.planned_end - s.planned_start).total_seconds() / 3600
        if s.status in ("completed", "in_progress", "scheduled"):
            planned_hours += Decimal(str(round(duration, 1)))
        if s.status in ("completed", "in_progress"):
            actual_hours += Decimal(str(round(duration, 1)))

    efficiency = float(actual_hours / planned_hours * 100) if planned_hours > 0 else 0.0

    return {
        "total_shifts": total,
        "completed_shifts": completed + in_progress,
        "missed_shifts": missed,
        "total_hours": actual_hours,
        "efficiency_percent": round(efficiency, 1),
    }


def generate_timesheet(db, department_id, period_start, period_end, generated_by):
    timesheet = Timesheet(
        id=uuid4(),
        department_id=department_id,
        period_start=period_start,
        period_end=period_end,
        status="draft",
        generated_by_user_id=generated_by,
        generated_at=datetime.utcnow(),
    )
    db.add(timesheet)
    db.flush()

    employees = (
        db.query(EmployeeView)
        .filter(
            EmployeeView.department_id == department_id,
            EmployeeView.status == "active",
        )
        .all()
    )

    for employee in employees:
        shifts = (
            db.query(ShiftAssignment)
            .filter(
                ShiftAssignment.employee_id == employee.id,
                ShiftAssignment.shift_date >= period_start,
                ShiftAssignment.shift_date <= period_end,
            )
            .all()
        )
        for shift in shifts:
            entry = _build_timesheet_entry(db, timesheet.id, employee.id, shift)
            db.add(entry)

    db.commit()
    db.refresh(timesheet)
    return timesheet


def _build_timesheet_entry(db, timesheet_id, employee_id, shift):
    records = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.shift_assignment_id == shift.id,
            AttendanceRecord.event_type == "granted",
        )
        .order_by(AttendanceRecord.event_at)
        .all()
    )

    check_ins  = [r for r in records if r.source != "exit"]
    check_outs = [r for r in records if r.source == "exit"]

    if not check_ins:
        return TimesheetEntry(
            id=uuid4(),
            timesheet_id=timesheet_id,
            employee_id=employee_id,
            work_date=shift.shift_date,
            time_kind="absence",
            regular_hours=Decimal("0"),
            night_hours=Decimal("0"),
            overtime_hours=Decimal("0"),
            was_manually_adjusted=False,
        )

    actual_start = check_ins[0].event_at
    actual_end   = check_outs[-1].event_at if check_outs else shift.planned_end
    worked       = (actual_end - actual_start).total_seconds()
    planned      = (shift.planned_end - shift.planned_start).total_seconds()
    regular      = Decimal(str(round(min(worked, planned) / 3600, 1)))
    overtime     = Decimal(str(round(max(0, (actual_end - shift.planned_end).total_seconds()) / 3600, 1)))
    night        = _calc_night_hours(actual_start, actual_end)

    return TimesheetEntry(
        id=uuid4(),
        timesheet_id=timesheet_id,
        employee_id=employee_id,
        work_date=shift.shift_date,
        time_kind="attendance",
        regular_hours=regular,
        night_hours=night,
        overtime_hours=overtime,
        was_manually_adjusted=False,
    )


def _calc_night_hours(start: datetime, end: datetime) -> Decimal:
    total = 0.0
    current = start
    while current < end:
        next_h = current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        interval_end = min(next_h, end)
        if current.hour >= 22 or current.hour < 6:
            total += (interval_end - current).total_seconds()
        current = interval_end
    return Decimal(str(round(total / 3600, 1)))