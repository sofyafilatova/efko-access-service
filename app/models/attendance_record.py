from sqlalchemy import Column, String, DateTime, Boolean, Integer, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.core.database import Base

class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees_view.id"), nullable=False)
    shift_assignment_id = Column(UUID(as_uuid=True), ForeignKey("shift_assignments.id"), nullable=True)
    access_point_id = Column(UUID(as_uuid=True), ForeignKey("access_points.id"), nullable=False)
    event_at = Column(DateTime, default=datetime.utcnow)
    event_type = Column(String, nullable=False)  # 'granted' or 'denied'
    source = Column(String, default="turnstile")
    deny_reason = Column(String, nullable=True)
    credential_id = Column(String, nullable=True)