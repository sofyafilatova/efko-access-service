from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class GuestPassCreate(BaseModel):
    guest_full_name: str
    guest_phone: str | None = None
    guest_company: str | None = None
    visit_purpose: str
    valid_from: datetime
    valid_until: datetime
    zone_ids: list[UUID]


class GuestPassRead(BaseModel):
    id: UUID
    invited_by_employee_id: UUID
    guest_full_name: str
    guest_phone: str | None
    guest_company: str | None
    visit_purpose: str
    valid_from: datetime
    valid_until: datetime
    status: str
    approved_by_user_id: UUID | None

    model_config = {"from_attributes": True}