import uuid
from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geography
from app.models.base import Base


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150))
    code: Mapped[str] = mapped_column(String(20), unique=True)
    address: Mapped[str | None] = mapped_column(String(255))
    geometry: Mapped[object | None] = mapped_column(Geography(geometry_type="POLYGON", srid=4326))
    center_point: Mapped[object | None] = mapped_column(Geography(geometry_type="POINT", srid=4326))
    access_level: Mapped[str | None] = mapped_column(String(20), default="restricted")
    parent_zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    access_points: Mapped[list["AccessPoint"]] = relationship("AccessPoint", back_populates="zone")


class AccessPoint(Base):
    __tablename__ = "access_points"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20))
    zone_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"))
    direction: Mapped[str | None] = mapped_column(String(10))
    controller_address: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    zone: Mapped["Zone"] = relationship("Zone", back_populates="access_points")