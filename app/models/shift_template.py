from sqlalchemy import Column, String, Time, Boolean, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from app.models.base import Base

class ShiftTemplate(Base):
    __tablename__ = "shift_templates"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    code = Column(String, nullable=False, unique=True)
    planned_start = Column(Time, nullable=False)
    planned_end = Column(Time, nullable=False)
    work_days_pattern = Column(String, default="1111100")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)