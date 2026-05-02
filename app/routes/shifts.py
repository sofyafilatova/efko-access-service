from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import (
    get_current_user, CurrentUser, AnyEmployee,
    ShiftManagerPlus, ManagerOnly
)
from app.models.shift import ShiftAssignment, Timesheet, TimesheetEntry
from app.schemas.shift import (
    ShiftAssignmentCreate, ShiftAssignmentRead,
    ShiftCalendarDay, MonthStats,
    TimesheetCreate, TimesheetRead, TimesheetEntryUpdate
)
from app.services.shift_service import (
    get_current_shift, get_calendar,
    get_month_stats, generate_timesheet
)

router = APIRouter(tags=["Shifts"])


def _auto_update_shift_status(db: Session, employee_id: UUID):
    """Автоматически обновляет статусы смен по текущему времени."""
    now = datetime.utcnow()
    shifts = db.query(ShiftAssignment).filter(
        ShiftAssignment.employee_id == employee_id
    ).all()
    changed = False
    for s in shifts:
        if s.status == "scheduled" and s.planned_start <= now <= s.planned_end:
            s.status = "in_progress"
            changed = True
        elif s.status in ("scheduled", "in_progress") and s.planned_end < now:
            s.status = "completed"
            changed = True
    if changed:
        db.commit()


@router.get("/shifts/current", response_model=ShiftAssignmentRead | None)
def current_shift(
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    lookup_id = user.employee_id or user.user_id
    _auto_update_shift_status(db, lookup_id)
    return get_current_shift(db, lookup_id)


@router.get("/shifts/calendar", response_model=list[ShiftCalendarDay])
def shift_calendar(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    lookup_id = user.employee_id or user.user_id
    _auto_update_shift_status(db, lookup_id)
    return get_calendar(db, lookup_id, year, month)


@router.get("/shifts/stats/month", response_model=MonthStats)
def month_stats(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    lookup_id = user.employee_id or user.user_id
    return get_month_stats(db, lookup_id, year, month)


class ExtendShiftRequest(BaseModel):
    hours: int  # на сколько часов продлить (1-12)


@router.patch("/shifts/current/extend")
def extend_current_shift(
    data: ExtendShiftRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    """Продление текущей смены. Пишет в shift_assignments и создаёт request."""
    if data.hours < 1 or data.hours > 12:
        raise HTTPException(400, "Hours must be between 1 and 12")

    lookup_id = user.employee_id or user.user_id
    now = datetime.utcnow()

    shift = db.query(ShiftAssignment).filter(
        ShiftAssignment.employee_id == lookup_id,
        ShiftAssignment.planned_start <= now,
        ShiftAssignment.planned_end >= now - timedelta(hours=1),
    ).first()

    if not shift:
        raise HTTPException(404, "No active shift to extend")

    old_end = shift.planned_end
    new_end = old_end + timedelta(hours=data.hours)
    shift.planned_end = new_end
    db.commit()
    db.refresh(shift)

    # Фиксируем в таблице requests
    from app.models.notification import Request
    req = Request(
        id=uuid4(),
        employee_id=lookup_id,
        type="extend_shift",
        status="approved",  # автоодобрено — сотрудник сам продлил
        payload={
            "shift_id": str(shift.id),
            "old_end": old_end.isoformat(),
            "new_end": new_end.isoformat(),
            "hours_added": data.hours,
        },
        created_at=now,
        processed_at=now,
    )
    db.add(req)
    db.commit()

    return {
        "shift_id": str(shift.id),
        "new_planned_end": new_end.isoformat(),
        "hours_added": data.hours,
    }


@router.get("/shifts/{shift_id}", response_model=ShiftAssignmentRead)
def get_shift(
    shift_id: UUID,
    db: Session = Depends(get_db),
    _: CurrentUser = ShiftManagerPlus
):
    shift = db.query(ShiftAssignment).filter(ShiftAssignment.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    return shift


@router.post("/shifts", response_model=ShiftAssignmentRead, status_code=201)
def create_shift(
    data: ShiftAssignmentCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = ManagerOnly
):
    existing = (
        db.query(ShiftAssignment)
        .filter(
            ShiftAssignment.employee_id == data.employee_id,
            ShiftAssignment.shift_date == data.shift_date,
        )
        .first()
    )
    if existing:
        raise HTTPException(409, f"Shift for {data.shift_date} already exists")

    shift = ShiftAssignment(
        id=uuid4(),
        employee_id=data.employee_id,
        shift_date=data.shift_date,
        planned_start=data.planned_start,
        planned_end=data.planned_end,
        shift_template_id=data.shift_template_id,
        status="scheduled",
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift


@router.post("/timesheets", response_model=TimesheetRead, status_code=201)
def create_timesheet(
    data: TimesheetCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = ManagerOnly
):
    existing = (
        db.query(Timesheet)
        .filter(
            Timesheet.department_id == data.department_id,
            Timesheet.period_start == data.period_start,
            Timesheet.period_end == data.period_end,
        )
        .first()
    )
    if existing:
        raise HTTPException(409, "Timesheet already exists")

    timesheet = generate_timesheet(
        db,
        department_id=data.department_id,
        period_start=data.period_start,
        period_end=data.period_end,
        generated_by=user.user_id,
    )
    return timesheet


@router.get("/timesheets", response_model=list[TimesheetRead])
def list_timesheets(
    department_id: UUID | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: CurrentUser = ManagerOnly
):
    q = db.query(Timesheet)
    if department_id:
        q = q.filter(Timesheet.department_id == department_id)
    if status:
        q = q.filter(Timesheet.status == status)
    return q.offset(offset).limit(limit).all()


@router.get("/timesheets/{timesheet_id}", response_model=TimesheetRead)
def get_timesheet(
    timesheet_id: UUID,
    db: Session = Depends(get_db),
    _: CurrentUser = ManagerOnly
):
    ts = db.query(Timesheet).filter(Timesheet.id == timesheet_id).first()
    if not ts:
        raise HTTPException(404, "Timesheet not found")
    return ts


@router.patch("/timesheets/{timesheet_id}/entries/{entry_id}")
def update_timesheet_entry(
    timesheet_id: UUID,
    entry_id: UUID,
    data: TimesheetEntryUpdate,
    db: Session = Depends(get_db),
    _: CurrentUser = ManagerOnly
):
    entry = (
        db.query(TimesheetEntry)
        .filter(
            TimesheetEntry.id == entry_id,
            TimesheetEntry.timesheet_id == timesheet_id,
        )
        .first()
    )
    if not entry:
        raise HTTPException(404, "Entry not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)

    entry.was_manually_adjusted = True
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/timesheets/{timesheet_id}/close")
def close_timesheet(
    timesheet_id: UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = ManagerOnly
):
    ts = db.query(Timesheet).filter(Timesheet.id == timesheet_id).first()
    if not ts:
        raise HTTPException(404, "Timesheet not found")
    if ts.status != "draft":
        raise HTTPException(409, f"Cannot close timesheet with status '{ts.status}'")

    ts.status = "closed"
    ts.closed_at = datetime.utcnow()
    db.commit()
    return {"id": timesheet_id, "status": "closed"}


@router.get("/timesheets/{timesheet_id}/csv")
def export_timesheet_csv(
    timesheet_id: UUID,
    db: Session = Depends(get_db),
    _: CurrentUser = ManagerOnly
):
    from fastapi.responses import StreamingResponse
    import csv, io
    ts = db.query(Timesheet).filter(Timesheet.id == timesheet_id).first()
    if not ts:
        raise HTTPException(404, "Timesheet not found")

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "ТабельныйНомер", "ФИО", "Дата", "ВидВремени",
        "КоличествоЧасов", "НочныеЧасы", "СверхурочныеЧасы",
        "РучнаяКорректировка"
    ])
    for entry in ts.entries:
        from app.models.employee import EmployeeView
        emp = db.query(EmployeeView).filter_by(id=entry.employee_id).first()
        writer.writerow([
            emp.personnel_number if emp else "",
            emp.full_name if emp else "",
            entry.work_date.strftime("%d.%m.%Y"),
            entry.time_kind,
            str(entry.regular_hours or 0),
            str(entry.night_hours or 0),
            str(entry.overtime_hours or 0),
            "Да" if entry.was_manually_adjusted else "Нет",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=timesheet.csv"}
    )