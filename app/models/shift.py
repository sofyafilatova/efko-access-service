import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, JSON, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base



class ShiftAssignment(Base):
    __tablename__ = "shift_assignments"

    __table_args__ = (
        UniqueConstraint("employee_id", "shift_date", name="uq_shift_employee_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees_view.id"))
    shift_template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("shift_templates.id"), nullable=True)
    shift_date: Mapped[date] = mapped_column(Date)
    planned_start: Mapped[datetime] = mapped_column(DateTime)
    planned_end: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    attendance_records: Mapped[list["AttendanceRecord"]] = relationship("AttendanceRecord", back_populates="shift_assignment")


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees_view.id"), nullable=True)
    shift_assignment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("shift_assignments.id"))
    access_point_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("access_points.id"))
    event_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    event_type: Mapped[str] = mapped_column(String(20))
    source: Mapped[str | None] = mapped_column(String(20))
    deny_reason: Mapped[str | None] = mapped_column(String(200))
    credential_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    shift_assignment: Mapped["ShiftAssignment | None"] = relationship("ShiftAssignment", back_populates="attendance_records")


class Timesheet(Base):
    __tablename__ = "timesheets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    department_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("departments_view.id"))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    generated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime)

    entries: Mapped[list["TimesheetEntry"]] = relationship("TimesheetEntry", back_populates="timesheet")


class TimesheetEntry(Base):
    __tablename__ = "timesheet_entries"

    __table_args__ = (
        UniqueConstraint("timesheet_id", "employee_id", "work_date", name="uq_timesheet_entry"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timesheet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("timesheets.id"))
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees_view.id"))
    work_date: Mapped[date] = mapped_column(Date)
    time_kind: Mapped[str] = mapped_column(String(20), default="attendance")
    regular_hours: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), default=0)
    night_hours: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), default=0)
    overtime_hours: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), default=0)
    was_manually_adjusted: Mapped[bool] = mapped_column(Boolean, default=False)
    adjustment_reason: Mapped[str | None] = mapped_column(String(500))

    timesheet: Mapped["Timesheet"] = relationship("Timesheet", back_populates="entries")