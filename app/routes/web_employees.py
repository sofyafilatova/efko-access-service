from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.employee import EmployeeView, PositionView, LocationView, WorkstationView

router = APIRouter(prefix="/web/employees", tags=["Web - Employees"])

@router.get("/list")
def list_employees_full(
    search: str | None = Query(None),
    location_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Список сотрудников с JOIN-ами."""
    
    q = db.query(
        EmployeeView.id,
        EmployeeView.personnel_number,
        EmployeeView.full_name,
        EmployeeView.status,
        EmployeeView.employment_type,
        PositionView.title.label("position_title"),
        PositionView.id.label("position_id"),
        LocationView.name.label("location_name"),
        LocationView.city.label("location_city"),
    ).outerjoin(PositionView, EmployeeView.position_id == PositionView.id)\
     .outerjoin(WorkstationView, EmployeeView.workstation_id == WorkstationView.id)\
     .outerjoin(LocationView, WorkstationView.location_id == LocationView.id)

    # Фильтры
    if status:
        q = q.filter(EmployeeView.status == status)
    if location_id:
        q = q.filter(LocationView.id == location_id)
    if search:
        q = q.filter(
            EmployeeView.full_name.ilike(f"%{search}%") |
            EmployeeView.personnel_number.ilike(f"%{search}%")
        )
    
    # СОРТИРОВКА - ДОБАВЬ ЭТУ СТРОЧКУ
    q = q.order_by(EmployeeView.full_name)

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
                "position_id": str(r.position_id) if r.position_id else None,
                "location": r.location_name or "—",
                "city": r.location_city or "—",
                "status": r.status,
                "employment_type": r.employment_type,
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