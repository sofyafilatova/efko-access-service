from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from app.models.shift import ShiftAssignment, AttendanceRecord, Timesheet, TimesheetEntry
from app.models.employee import EmployeeView


def get_current_shift(db: Session, employee_id: UUID) -> ShiftAssignment | None:
    """Текущая активная смена сотрудника."""
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
    """Смены за месяц для календаря мобилки."""
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

    shift_map = {s.shift_date: s for s in shifts}
    result = []
    current = start
    while current <= end:
        result.append({
            "date": current,
            "has_shift": current in shift_map,
            "shift": shift_map.get(current),
        })
        current += timedelta(days=1)
    return result


def get_month_stats(db: Session, employee_id: UUID, year: int, month: int) -> dict:
    """Статистика за месяц — считаем из реальных данных смен."""
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

    # Считаем плановые часы из назначенных смен
    planned_hours = Decimal(0)
    for s in shifts:
        if s.status in ("completed", "in_progress", "scheduled"):
            duration = (s.planned_end - s.planned_start).total_seconds() / 3600
            planned_hours += Decimal(str(round(duration, 1)))

    # Считаем фактические часы из attendance_records
    actual_hours = Decimal(0)
    for s in shifts:
        records = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.shift_assignment_id == s.id,
                AttendanceRecord.event_type == "granted",
            )
            .order_by(AttendanceRecord.event_at)
            .all()
        )
        check_ins = [r for r in records if r.source != "exit"]
        check_outs = [r for r in records if r.source == "exit"]
        if check_ins:
            start_time = check_ins[0].event_at
            end_time = check_outs[-1].event_at if check_outs else s.planned_end
            hours = (end_time - start_time).total_seconds() / 3600
            actual_hours += Decimal(str(round(hours, 1)))

    # Если нет attendance_records — используем плановые часы для completed/in_progress
    if actual_hours == 0 and (completed + in_progress) > 0:
        for s in shifts:
            if s.status in ("completed", "in_progress"):
                duration = (s.planned_end - s.planned_start).total_seconds() / 3600
                actual_hours += Decimal(str(round(duration, 1)))

    efficiency = float(actual_hours / planned_hours * 100) if planned_hours > 0 else 0.0

    return {
        "total_shifts": total,
        "completed_shifts": completed + in_progress,
        "missed_shifts": missed,
        "total_hours": actual_hours,
        "efficiency_percent": round(efficiency, 1),
    }


def generate_timesheet(
    db: Session,
    department_id: UUID,
    period_start: date,
    period_end: date,
    generated_by: UUID,
) -> Timesheet:
    """
    Генерация табеля за период.
    Проходит по всем сменам отдела, считает часы из attendance_records.
    """
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
    db.flush()  # получаем id до commit

    # Все сотрудники отдела
    employees = (
        db.query(EmployeeView)
        .filter(
            EmployeeView.department_id == department_id,
            EmployeeView.status == "active",
        )
        .all()
    )

    for employee in employees:
        # Смены сотрудника за период
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


def _build_timesheet_entry(
    db: Session,
    timesheet_id: UUID,
    employee_id: UUID,
    shift: ShiftAssignment,
) -> TimesheetEntry:
    """
    Считает часы одного дня из attendance_records.
    Логика: последний check_out - первый check_in = regular_hours.
    Ночные: пересечение с 22:00-06:00.
    Сверхурочные: всё после planned_end.
    """
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

    check_ins = [r for r in records if r.source != "exit"]
    check_outs = [r for r in records if r.source == "exit"]

    if not check_ins:
        # Нет прихода — прогул
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
    actual_end = check_outs[-1].event_at if check_outs else shift.planned_end

    # Основные часы (не больше плановых)
    worked_seconds = (actual_end - actual_start).total_seconds()
    planned_seconds = (shift.planned_end - shift.planned_start).total_seconds()
    regular_seconds = min(worked_seconds, planned_seconds)
    regular_hours = Decimal(str(round(regular_seconds / 3600, 1)))

    # Сверхурочные
    overtime_seconds = max(0, (actual_end - shift.planned_end).total_seconds())
    overtime_hours = Decimal(str(round(overtime_seconds / 3600, 1)))

    # Ночные (22:00-06:00)
    night_hours = _calc_night_hours(actual_start, actual_end)

    return TimesheetEntry(
        id=uuid4(),
        timesheet_id=timesheet_id,
        employee_id=employee_id,
        work_date=shift.shift_date,
        time_kind="attendance",
        regular_hours=regular_hours,
        night_hours=night_hours,
        overtime_hours=overtime_hours,
        was_manually_adjusted=False,
    )


def _calc_night_hours(start: datetime, end: datetime) -> Decimal:
    """Считает пересечение интервала работы с ночным временем 22:00-06:00."""
    total_night = 0.0
    current = start

    while current < end:
        next_hour = current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        interval_end = min(next_hour, end)
        hour = current.hour
        if hour >= 22 or hour < 6:
            total_night += (interval_end - current).total_seconds()
        current = interval_end

    return Decimal(str(round(total_night / 3600, 1)))