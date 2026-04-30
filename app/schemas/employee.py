from pydantic import BaseModel
from uuid import UUID
from datetime import date, datetime


class DepartmentRead(BaseModel):
    id: UUID
    name: str
    code: str
    type: str | None

    model_config = {"from_attributes": True}


class PositionRead(BaseModel):
    id: UUID
    title: str
    code: str | None

    model_config = {"from_attributes": True}


class EmployeeProfileRead(BaseModel):
    last_name: str | None
    first_name: str | None
    patronymic: str | None
    phone: str | None
    avatar_url: str | None

    model_config = {"from_attributes": True}


class EmployeeRead(BaseModel):
    id: UUID
    personnel_number: str
    full_name: str
    status: str | None
    employment_type: str | None
    hire_date: date | None
    department: DepartmentRead | None
    position: PositionRead | None
    profile: EmployeeProfileRead | None

    model_config = {"from_attributes": True}


class EmployeeProfileUpdate(BaseModel):
    last_name: str | None = None
    first_name: str | None = None
    patronymic: str | None = None
    phone: str | None = None
    avatar_url: str | None = None