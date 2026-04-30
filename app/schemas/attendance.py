from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class CheckInRequest(BaseModel):
    token_value: str          # номер карты или QR-токен
    access_point_id: UUID
    source: str = "rfid"      # rfid / qr / manual
    event_at: datetime | None = None   # если None — берём utcnow()


class CheckInResponse(BaseModel):
    result: str               # granted / denied
    employee_id: UUID | None
    employee_name: str | None
    shift_id: UUID | None
    deny_reason: str | None


class AttendanceRecordRead(BaseModel):
    id: UUID
    employee_id: UUID
    access_point_id: UUID
    event_at: datetime
    event_type: str
    source: str
    deny_reason: str | None

    model_config = {"from_attributes": True}