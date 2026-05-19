from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID, uuid4
from datetime import datetime
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.models.access import AccessRight
from app.models.notification import Notification
from app.models.zone import Zone

router = APIRouter(prefix="/access-rights", tags=["Access Rights"])

class AccessRightCreate(BaseModel):
    zone_id: UUID
    is_permitted: bool
    granted_by_user_id: UUID
    reason: str | None = None


@router.get("/")
def get_access_rights(
    employee_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    """Список прав сотрудника на зоны"""
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
    employee_id: UUID = Query(...),  # ← ПЕРЕМЕСТИЛИ СЮДА ИЗ ТЕЛА
    data: AccessRightCreate,
    db: Session = Depends(get_db),
):
    """Выдать или отозвать доступ сотрудника к зоне"""
    
    # Получаем название зоны
    zone = db.query(Zone).filter(Zone.id == data.zone_id).first()
    zone_name = zone.name if zone else "неизвестная зона"
    
    existing = db.query(AccessRight).filter(
        AccessRight.employee_id == employee_id,
        AccessRight.zone_id == data.zone_id,
    ).first()
    
    if existing:
        old_status = existing.is_permitted
        existing.is_permitted = data.is_permitted
        existing.granted_by_user_id = data.granted_by_user_id
        existing.reason = data.reason
        existing.granted_at = datetime.utcnow()
        db.commit()
        
        # Отправляем уведомление только если статус изменился
        if old_status != data.is_permitted:
            create_notification(db, employee_id, data.is_permitted, zone_name, data.reason)
        
        return {"message": "updated"}
    else:
        new_right = AccessRight(
            id=uuid4(),
            employee_id=employee_id,
            zone_id=data.zone_id,
            is_permitted=data.is_permitted,
            granted_by_user_id=data.granted_by_user_id,
            granted_at=datetime.utcnow(),
            reason=data.reason,
        )
        db.add(new_right)
        db.commit()
        
        # Отправляем уведомление о выдаче права
        if data.is_permitted:
            create_notification(db, employee_id, data.is_permitted, zone_name, data.reason)
        
        return {"message": "created"}


def create_notification(db: Session, employee_id: UUID, is_permitted: bool, zone_name: str, reason: str | None):
    """Создаёт уведомление для сотрудника об изменении прав доступа"""
    
    if is_permitted:
        title = "🔓 Доступ выдан"
        body = f"Вам выдан доступ в зону: {zone_name}"
        if reason:
            body += f"\nПричина: {reason}"
    else:
        title = "🔒 Доступ отозван"
        body = f"У вас отозван доступ в зону: {zone_name}"
        if reason:
            body += f"\nПричина: {reason}"
    
    notification = Notification(
        id=uuid4(),
        employee_id=employee_id,
        title=title,
        body=body,
        category="access_rights",
        is_read=False,
        created_at=datetime.utcnow()
    )
    db.add(notification)
    db.commit()