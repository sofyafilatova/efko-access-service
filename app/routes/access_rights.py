from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID, uuid4
from datetime import datetime
from pydantic import BaseModel
from app.core.database import get_db
from app.core.security import AnyEmployee, CurrentUser
from app.models.access import AccessRight

router = APIRouter(prefix="/access-rights", tags=["Access Rights"])

class AccessRightCreate(BaseModel):
    employee_id: UUID
    zone_id: UUID
    is_permitted: bool
    granted_by_user_id: UUID
    reason: str | None = None


@router.get("/")
def get_access_rights(
    employee_id: UUID = Query(...),
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee,
):
    """Список прав сотрудника на зоны (для веб-панели)"""
    rights = db.query(AccessRight).filter(AccessRight.employee_id == employee_id).all()
    return [
        {
            "id": str(r.id),
            "employee_id": str(r.employee_id),
            "zone_id": str(r.zone_id),
            "is_permitted": r.is_permitted,
            "granted_at": r.granted_at.isoformat() if r.granted_at else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "reason": r.reason,
        }
        for r in rights
    ]


@router.post("/")
def create_or_update_access_right(
    data: AccessRightCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee,
):
    """Выдать или отозвать доступ сотрудника к зоне"""
    existing = db.query(AccessRight).filter(
        AccessRight.employee_id == data.employee_id,
        AccessRight.zone_id == data.zone_id,
    ).first()
    
    if existing:
        existing.is_permitted = data.is_permitted
        existing.granted_by_user_id = data.granted_by_user_id
        existing.reason = data.reason
        existing.granted_at = datetime.utcnow()
        db.commit()
        return {"message": "updated"}
    else:
        new_right = AccessRight(
            id=uuid4(),
            employee_id=data.employee_id,
            zone_id=data.zone_id,
            is_permitted=data.is_permitted,
            granted_by_user_id=data.granted_by_user_id,
            granted_at=datetime.utcnow(),
            reason=data.reason,
        )
        db.add(new_right)
        db.commit()
        return {"message": "created"}