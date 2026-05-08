from sqlalchemy import Column, String, Boolean
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import Base
import uuid

class AccessPoint(Base):
    __tablename__ = "access_points"
    __table_args__ = {'extend_existing': True}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # 'turnstile', 'door', 'gate'
    zone_id = Column(UUID(as_uuid=True), nullable=False)
    direction = Column(String, default="both")  # 'in', 'out', 'both'
    controller_address = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)