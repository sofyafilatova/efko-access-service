from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text
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
    PositionView, DepartmentView, LocationView, WorkstationView
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
    
    lookup_id = user.employee_id or user.user_id
    
    # Получаем локацию через прямой SQL (чтобы использовать COALESCE)
    query = text("""
        SELECT 
            e.id,
            e.personnel_number,
            e.full_name,
            e.status,
            e.employment_type,
            e.hire_date,
            e.date_of_birth,
            p.title as position_title,
            d.name as department_name,
            COALESCE(l.name, wl.name) as location_name,
            COALESCE(l.street_address, wl.street_address) as location_address,
            COALESCE(l.city, wl.city) as location_city,
            ep.phone,
            ep.last_name,
            ep.first_name,
            ep.patronymic
        FROM employees_view e
        LEFT JOIN positions_view p ON e.position_id = p.id
        LEFT JOIN departments_view d ON e.department_id = d.id
        LEFT JOIN locations_view l ON e.location_id = l.id
        LEFT JOIN workstations_view w ON e.workstation_id = w.id
        LEFT JOIN locations_view wl ON w.location_id = wl.id
        LEFT JOIN employee_profiles ep ON e.id = ep.employee_id
        WHERE e.id = :employee_id
    """)
    
    result = db.execute(query, {"employee_id": lookup_id}).fetchone()
    
    if not result:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    
    # Распаковываем результат
    (
        emp_id, personnel_number, full_name, status, employment_type,
        hire_date, date_of_birth, position_title, department_name,
        location_name, location_address, location_city,
        phone, last_name, first_name, patronymic
    ) = result
    
    return {
        "id": str(emp_id),
        "personnel_number": personnel_number,
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "patronymic": patronymic,
        "phone": phone,
        "status": status,
        "employment_type": employment_type,
        "hire_date": hire_date.isoformat() if hire_date else None,
        "date_of_birth": date_of_birth.isoformat() if date_of_birth else None,
        "position": {
            "title": position_title or "—"
        },
        "department": {
            "name": department_name or "—"
        },
        "location": {
            "name": location_name or "—",
            "address": location_address or "—",
            "city": location_city or "—"
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