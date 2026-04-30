from pydantic import BaseModel
from uuid import UUID
from datetime import datetime, date


class RequestCreate(BaseModel):
    type: str
    payload: dict


class RequestRead(BaseModel):
    id: UUID
    employee_id: UUID
    type: str
    status: str
    payload: dict | None
    admin_comment: str | None
    processed_by_user_id: UUID | None
    created_at: datetime
    processed_at: datetime | None

    model_config = {"from_attributes": True}


class RequestApprove(BaseModel):
    admin_comment: str | None = None


class RequestReject(BaseModel):
    admin_comment: str