from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.employee import (
    EmployeeView, PositionView, LocationView, EmployeeProfile
)

router = APIRouter(prefix="/web/employees", tags=["Web - Employees"])


@router.get("/list")
def list_employees_full(
    search: str | None = Query(None),
    location_id: str | None = None,
    status: str | None = "active",
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Список сотрудников с JOIN — только для веб-панели HR."""
    q = (
        db.query(
            EmployeeView.id,
            EmployeeView.personnel_number,
            EmployeeView.full_name,
            EmployeeView.status,
            EmployeeView.employment_type,
            EmployeeView.hire_date,
            EmployeeView.location_id,
            PositionView.title.label("position_title"),
            LocationView.name.label("location_name"),
            LocationView.city.label("location_city"),
            EmployeeProfile.phone,
        )
        .outerjoin(PositionView, EmployeeView.position_id == PositionView.id)
        .outerjoin(LocationView, EmployeeView.location_id == LocationView.id)
        .outerjoin(EmployeeProfile, EmployeeView.id == EmployeeProfile.employee_id)
    )

    if status:
        q = q.filter(EmployeeView.status == status)
    if location_id:
        q = q.filter(EmployeeView.location_id == location_id)
    if search:
        q = q.filter(
            EmployeeView.full_name.ilike(f"%{search}%") |
            EmployeeView.personnel_number.ilike(f"%{search}%")
        )

    total = q.count()
    rows = q.offset(offset).limit(limit).all()

    return {
        "total": total,
        "items": [
            {
                "id": str(r.id),
                "personnel_number": r.personnel_number,
                "full_name": r.full_name,
                "position": r.position_title or "—",
                "location": r.location_name or "—",
                "city": r.location_city or "—",
                "phone": r.phone or "—",
                "status": r.status,
                "employment_type": r.employment_type,
                "hire_date": r.hire_date.isoformat() if r.hire_date else None,
            }
            for r in rows
        ],
    }


@router.get("/locations")
def list_locations(db: Session = Depends(get_db)):
    """Список офисов/заводов для фильтра."""
    locs = db.query(LocationView).order_by(LocationView.name).all()
    return [
        {
            "id": str(l.id),
            "name": l.name,
            "city": l.city or "—",
            "type": l.type,
        }
        for l in locs
    ]