from pydantic import BaseModel
from uuid import UUID
from datetime import date, datetime
from decimal import Decimal


class ShiftAssignmentCreate(BaseModel):
    employee_id: UUID
    shift_date: date
    planned_start: datetime
    planned_end: datetime
    shift_template_id: UUID | None = None


class ShiftAssignmentRead(BaseModel):
    id: UUID
    employee_id: UUID
    shift_date: date
    planned_start: datetime
    planned_end: datetime
    status: str
    shift_template_id: UUID | None

    model_config = {"from_attributes": True}


class ShiftCalendarDay(BaseModel):
    date: date
    has_shift: bool
    shift: ShiftAssignmentRead | None


class TimesheetCreate(BaseModel):
    department_id: UUID
    period_start: date
    period_end: date


class TimesheetEntryRead(BaseModel):
    id: UUID
    employee_id: UUID
    work_date: date
    time_kind: str
    regular_hours: Decimal
    night_hours: Decimal
    overtime_hours: Decimal
    was_manually_adjusted: bool
    adjustment_reason: str | None

    model_config = {"from_attributes": True}


class TimesheetEntryUpdate(BaseModel):
    time_kind: str | None = None
    regular_hours: Decimal | None = None
    night_hours: Decimal | None = None
    overtime_hours: Decimal | None = None
    adjustment_reason: str

    
class TimesheetRead(BaseModel):
    id: UUID
    department_id: UUID
    period_start: date
    period_end: date
    status: str
    generated_at: datetime | None
    closed_at: datetime | None
    exported_at: datetime | None
    entries: list[TimesheetEntryRead] = []

    model_config = {"from_attributes": True}


class MonthStats(BaseModel):
    total_shifts: int
    completed_shifts: int
    missed_shifts: int
    total_hours: Decimal
    efficiency_percent: float