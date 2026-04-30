from pydantic import BaseModel, field_validator
from uuid import UUID
from datetime import datetime


class ResourceRead(BaseModel):
    id: UUID
    label: str
    type: str
    floor: int | None
    capacity: int | None
    zone_id: UUID
    is_active: bool

    model_config = {"from_attributes": True}


class BookingCreate(BaseModel):
    resource_id: UUID
    start_at: datetime
    end_at: datetime
    notes: str | None = None

    @field_validator("end_at")
    @classmethod
    def end_after_start(cls, v, info):
        if "start_at" in info.data and v <= info.data["start_at"]:
            raise ValueError("end_at must be after start_at")
        return v


class BookingRead(BaseModel):
    id: UUID
    employee_id: UUID
    resource_id: UUID
    start_at: datetime
    end_at: datetime
    status: str
    created_at: datetime
    cancelled_at: datetime | None

    model_config = {"from_attributes": True}


class QRResponse(BaseModel):
    credential_id: UUID
    token_value: str
    expires_at: datetime | None
    qr_data: str        # строка которую рендерить в QR