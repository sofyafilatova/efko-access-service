import uuid
from datetime import datetime, date
from sqlalchemy import String, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class DepartmentView(Base):
    __tablename__ = "departments_view"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150))
    code: Mapped[str] = mapped_column(String(20), unique=True)
    type: Mapped[str | None] = mapped_column(String(20))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments_view.id"))
    head_employee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    employees: Mapped[list["EmployeeView"]] = relationship("EmployeeView", back_populates="department")


class PositionView(Base):
    __tablename__ = "positions_view"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(150))
    code: Mapped[str | None] = mapped_column(String(20))
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments_view.id"))

    employees: Mapped[list["EmployeeView"]] = relationship("EmployeeView", back_populates="position")


class EmployeeView(Base):
    __tablename__ = "employees_view"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    personnel_number: Mapped[str] = mapped_column(String(10), unique=True)
    full_name: Mapped[str] = mapped_column(String(150))
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments_view.id"))
    position_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("positions_view.id"))
    employment_type: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str | None] = mapped_column(String(20), default="active")
    hire_date: Mapped[date | None] = mapped_column(Date)
    termination_date: Mapped[date | None] = mapped_column(Date)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    department: Mapped["DepartmentView | None"] = relationship("DepartmentView", back_populates="employees")
    position: Mapped["PositionView | None"] = relationship("PositionView", back_populates="employees")
    profile: Mapped["EmployeeProfile | None"] = relationship("EmployeeProfile", back_populates="employee", uselist=False)


class EmployeeProfile(Base):
    __tablename__ = "employee_profiles"

    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees_view.id"), primary_key=True)
    last_name: Mapped[str | None] = mapped_column(String(50))
    first_name: Mapped[str | None] = mapped_column(String(50))
    patronymic: Mapped[str | None] = mapped_column(String(50))
    phone: Mapped[str | None] = mapped_column(String(20))
    avatar_url: Mapped[str | None] = mapped_column(String)
    preferred_locale: Mapped[str | None] = mapped_column(String(10), default="ru")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)

    employee: Mapped["EmployeeView"] = relationship("EmployeeView", back_populates="profile")