from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class NotificationRead(BaseModel):
    id: UUID
    title: str
    body: str
    category: str | None
    is_read: bool
    created_at: datetime
    read_at: datetime | None

    model_config = {"from_attributes": True}


class DeviceTokenCreate(BaseModel):
    platform: str        # ios / android
    fcm_token: str
    app_version: str | None = None