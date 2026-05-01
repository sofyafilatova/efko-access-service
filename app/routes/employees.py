from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from uuid import UUID

from app.core.database import get_db
from app.core.security import (
    get_current_user, CurrentUser, AnyEmployee,
    ShiftManagerPlus, AdminOnly
)
from app.models.employee import EmployeeView, EmployeeProfile
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


@router.get("/me", response_model=EmployeeRead)
def get_my_profile(
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    """Текущий сотрудник — для главного экрана и профиля мобилки."""
    employee = (
        _base_query(db)
        .filter(EmployeeView.id == user.user_id)
        .first()
    )
    if not employee:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    return employee


@router.patch("/me/profile", response_model=EmployeeRead)
def update_my_profile(
    data: EmployeeProfileUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    """Сотрудник редактирует свой профиль (имя, телефон, аватар)."""
    employee = db.query(EmployeeView).filter(EmployeeView.id == user.user_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    profile = db.query(EmployeeProfile).filter(
        EmployeeProfile.employee_id == user.user_id
    ).first()

    if not profile:
        profile = EmployeeProfile(employee_id=user.user_id)
        db.add(profile)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)

    db.commit()

    return _base_query(db).filter(EmployeeView.id == user.user_id).first()


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