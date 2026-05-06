from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.employee import EmployeeView

router = APIRouter(prefix="/web/employees", tags=["Web - Employees"])

@router.get("/list")
def list_employees(
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    employees = db.query(EmployeeView).offset(offset).limit(limit).all()
    result = []
    for emp in employees:
        result.append({
            "id": str(emp.id),
            "personnel_number": emp.personnel_number,
            "full_name": emp.full_name,
            "position": None,
            "location": None,
            "status": emp.status,
        })
    return {"total": len(result), "items": result}