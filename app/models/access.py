import uuid
from datetime import datetime, date
from sqlalchemy import String, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, JSON, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class AccessCard(Base):
    __tablename__ = "access_cards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees_view.id"))
    card_number: Mapped[str] = mapped_column(String(20), unique=True)
    card_type: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="active")
    issued_at: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date)
    blocked_reason: Mapped[str | None] = mapped_column(String(200))


class AccessRight(Base):
    __tablename__ = "access_rights"

    __table_args__ = (
        UniqueConstraint("employee_id", "zone_id", name="uq_access_rights_employee_zone"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees_view.id"))
    zone_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"))
    is_permitted: Mapped[bool] = mapped_column(Boolean, default=True)
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    reason: Mapped[str | None] = mapped_column(String(500))


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_type: Mapped[str] = mapped_column(String(20))
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    token_value: Mapped[str] = mapped_column(String(64), unique=True)
    medium: Mapped[str] = mapped_column(String(10))
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)