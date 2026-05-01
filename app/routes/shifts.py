from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID, uuid4
from datetime import datetime

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

import asyncio
from app.core.rabbitmq import publish_event

router = APIRouter(tags=["Shifts"])


# ─── Смены ────────────────────────────────────────────────────────────────────

@router.get("/shifts/current", response_model=ShiftAssignmentRead | None)
def current_shift(
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    lookup_id = user.employee_id or user.user_id
    return get_current_shift(db, lookup_id) 


@router.get("/shifts/calendar", response_model=list[ShiftCalendarDay])
def shift_calendar(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    lookup_id = user.employee_id or user.user_id
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
    """Назначить смену сотруднику."""
    existing = (
        db.query(ShiftAssignment)
        .filter(
            ShiftAssignment.employee_id == data.employee_id,
            ShiftAssignment.shift_date == data.shift_date,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Shift for {data.shift_date} already exists for this employee"
        )

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


# ─── Табели ───────────────────────────────────────────────────────────────────

@router.post("/timesheets", response_model=TimesheetRead, status_code=201)
def create_timesheet(
    data: TimesheetCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = ManagerOnly
):
    """Сформировать табель за период. Статус: draft."""
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
        raise HTTPException(
            status_code=409,
            detail="Timesheet for this department and period already exists"
        )

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
        raise HTTPException(status_code=404, detail="Timesheet not found")
    return ts


@router.patch("/timesheets/{timesheet_id}/entries/{entry_id}")
def update_timesheet_entry(
    timesheet_id: UUID,
    entry_id: UUID,
    data: TimesheetEntryUpdate,
    db: Session = Depends(get_db),
    _: CurrentUser = ManagerOnly
):
    """HR вручную корректирует строку табеля."""
    entry = (
        db.query(TimesheetEntry)
        .filter(
            TimesheetEntry.id == entry_id,
            TimesheetEntry.timesheet_id == timesheet_id,
        )
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

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
    """Закрыть табель. После закрытия редактирование недоступно."""
    ts = db.query(Timesheet).filter(Timesheet.id == timesheet_id).first()
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    if ts.status != "draft":
        raise HTTPException(status_code=409, detail=f"Cannot close timesheet with status '{ts.status}'")

    ts.status = "closed"
    ts.closed_at = datetime.utcnow()
    db.commit()

    try:
        loop = asyncio.get_event_loop()
        loop.create_task(publish_event("access.timesheet.closed", {
            "timesheet_id": str(timesheet_id),
            "department_id": str(ts.department_id),
            "period_start": str(ts.period_start),
            "period_end": str(ts.period_end),
            "closed_at": ts.closed_at.isoformat(),
        }))
    except Exception:
        pass
    return {"id": timesheet_id, "status": "closed"}


@router.get("/timesheets/{timesheet_id}/csv")
def export_timesheet_csv(
    timesheet_id: UUID,
    db: Session = Depends(get_db),
    _: CurrentUser = ManagerOnly
):
    """Экспорт табеля в CSV для 1С:ЗУП."""
    from fastapi.responses import StreamingResponse
    import csv
    import io

    ts = db.query(Timesheet).filter(Timesheet.id == timesheet_id).first()
    if not ts:
        raise HTTPException(status_code=404, detail="Timesheet not found")

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "ТабельныйНомер", "ФИО", "Дата", "ВидВремени",
        "КоличествоЧасов", "НочныеЧасы", "СверхурочныеЧасы",
        "РучнаяКорректировка", "Причина"
    ])

    for entry in ts.entries:
        employee = db.query(
            __import__('app.models.employee', fromlist=['EmployeeView']).EmployeeView
        ).filter_by(id=entry.employee_id).first()

        writer.writerow([
            employee.personnel_number if employee else "",
            employee.full_name if employee else "",
            entry.work_date.strftime("%d.%m.%Y"),
            entry.time_kind,
            str(entry.regular_hours or 0),
            str(entry.night_hours or 0),
            str(entry.overtime_hours or 0),
            "Да" if entry.was_manually_adjusted else "Нет",
            entry.adjustment_reason or "",
        ])

    output.seek(0)
    filename = f"timesheet_{ts.period_start}_{ts.period_end}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )