from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class ZoneCreate(BaseModel):
    name: str
    code: str
    address: str | None = None
    access_level: str = "restricted"
    parent_zone_id: UUID | None = None


class ZoneUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    access_level: str | None = None
    is_active: bool | None = None


class ZoneRead(BaseModel):
    id: UUID
    name: str
    code: str
    address: str | None
    access_level: str | None
    parent_zone_id: UUID | None
    is_active: bool

    model_config = {"from_attributes": True}