from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from uuid import UUID
from datetime import date
from typing import Optional

from app.core.database import get_db
from app.core.security import (
    get_current_user, CurrentUser, AnyEmployee,
    ShiftManagerPlus, AdminOnly
)
from app.models.employee import (
    EmployeeView, EmployeeProfile, 
    PositionView, DepartmentView, LocationView
)
from app.schemas.employee import EmployeeRead, EmployeeProfileUpdate

router = APIRouter(prefix="/employees", tags=["Employees"])


def _base_query(db: Session):
    return (
        db.query(EmployeeView)
        .options(
            joinedload(EmployeeView.department),
            joinedload(EmployeeView.position),
            joinedload(EmployeeView.profile),
        )
    )


@router.get("/me")
def get_my_profile(
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    """Профиль текущего сотрудника с JOINs для мобилки."""
    
    # Используем employee_id из токена, если есть
    lookup_id = user.employee_id or user.user_id
    
    # Делаем запрос с JOINами напрямую (не через options)
    emp = db.query(
        EmployeeView.id,
        EmployeeView.personnel_number,
        EmployeeView.full_name,
        EmployeeView.status,
        EmployeeView.employment_type,
        EmployeeView.hire_date,
        EmployeeView.date_of_birth,
        PositionView.title.label("position_title"),
        DepartmentView.name.label("department_name"),
        LocationView.name.label("location_name"),
        LocationView.street_address.label("location_address"),
        LocationView.city.label("location_city"),
        EmployeeProfile.phone,
        EmployeeProfile.last_name,
        EmployeeProfile.first_name,
        EmployeeProfile.patronymic,
    ).outerjoin(
        PositionView, EmployeeView.position_id == PositionView.id
    ).outerjoin(
        DepartmentView, EmployeeView.department_id == DepartmentView.id
    ).outerjoin(
        LocationView, EmployeeView.location_id == LocationView.id
    ).outerjoin(
        EmployeeProfile, EmployeeView.id == EmployeeProfile.employee_id
    ).filter(
        EmployeeView.id == lookup_id
    ).first()

    if not emp:
        raise HTTPException(status_code=404, detail="Employee profile not found")

    return {
        "id": str(emp.id),
        "personnel_number": emp.personnel_number,
        "full_name": emp.full_name,
        "first_name": emp.first_name,
        "last_name": emp.last_name,
        "patronymic": emp.patronymic,
        "phone": emp.phone,
        "status": emp.status,
        "employment_type": emp.employment_type,
        "hire_date": emp.hire_date.isoformat() if emp.hire_date else None,
        "date_of_birth": emp.date_of_birth.isoformat() if emp.date_of_birth else None,
        "position": {
            "title": emp.position_title or "—"
        },
        "department": {
            "name": emp.department_name or "—"
        },
        "location": {
            "name": emp.location_name or "—",
            "address": emp.location_address or "—",
            "city": emp.location_city or "—"
        }
    }


@router.patch("/me/profile", response_model=EmployeeRead)
def update_my_profile(
    data: EmployeeProfileUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    lookup_id = user.employee_id or user.user_id
    employee = db.query(EmployeeView).filter(EmployeeView.id == lookup_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    profile = db.query(EmployeeProfile).filter(
        EmployeeProfile.employee_id == lookup_id
    ).first()
    if not profile:
        profile = EmployeeProfile(employee_id=lookup_id)
        db.add(profile)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)

    db.commit()
    return _base_query(db).filter(EmployeeView.id == lookup_id).first() 


@router.get("/", response_model=list[EmployeeRead])
def list_employees(
    search: str | None = Query(None, description="Поиск по ФИО или табельному номеру"),
    department_id: UUID | None = None,
    status: str | None = "active",
    limit: int = Query(20, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: CurrentUser = ShiftManagerPlus
):
    """Список сотрудников — для веб-админки."""
    q = _base_query(db)

    if status:
        q = q.filter(EmployeeView.status == status)
    if department_id:
        q = q.filter(EmployeeView.department_id == department_id)
    if search:
        q = q.filter(
            EmployeeView.full_name.ilike(f"%{search}%") |
            EmployeeView.personnel_number.ilike(f"%{search}%")
        )

    return q.offset(offset).limit(limit).all()


@router.get("/{employee_id}", response_model=EmployeeRead)
def get_employee(
    employee_id: UUID,
    db: Session = Depends(get_db),
    _: CurrentUser = AnyEmployee
):
    employee = _base_query(db).filter(EmployeeView.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    return employee