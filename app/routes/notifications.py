from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from uuid import UUID, uuid4
from datetime import datetime

from app.core.database import get_db
from app.core.security import AnyEmployee, CurrentUser
from app.models.notification import Notification, DeviceToken
from app.schemas.notification import NotificationRead, DeviceTokenCreate

router = APIRouter(tags=["Notifications"])


@router.get("/notifications", response_model=list[NotificationRead])
def list_notifications(
    is_read: bool | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    lookup_id = user.employee_id or user.user_id
    q = db.query(Notification).filter(Notification.employee_id == lookup_id)
    if is_read is not None:
        q = q.filter(Notification.is_read == is_read)
    return q.order_by(Notification.created_at.desc()).offset(offset).limit(limit).all()


@router.patch("/notifications/{notification_id}/read")
def mark_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    lookup_id = user.employee_id or user.user_id
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.employee_id == lookup_id,
    ).first()
    if not notif:
        return {"ok": False}

    notif.is_read = True
    notif.read_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.patch("/notifications/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    lookup_id = user.employee_id or user.user_id
    now = datetime.utcnow()
    db.query(Notification).filter(
        Notification.employee_id == lookup_id,
        Notification.is_read == False,
    ).update({"is_read": True, "read_at": now})
    db.commit()
    return {"ok": True}


@router.post("/device-tokens", status_code=201)
def register_device_token(
    data: DeviceTokenCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    """Регистрация устройства для push-уведомлений."""
    lookup_id = user.employee_id or user.user_id
    existing = db.query(DeviceToken).filter(
        DeviceToken.fcm_token == data.fcm_token
    ).first()

    if existing:
        existing.employee_id = lookup_id
        existing.last_seen_at = datetime.utcnow()
        existing.app_version = data.app_version
        db.commit()
        return {"ok": True, "action": "updated"}

    token = DeviceToken(
        id=uuid4(),
        employee_id=lookup_id,
        platform=data.platform,
        fcm_token=data.fcm_token,
        app_version=data.app_version,
        registered_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
    )
    db.add(token)
    db.commit()
    return {"ok": True, "action": "created"}


@router.delete("/device-tokens")
def unregister_device_token(
    fcm_token: str = Query(...),
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    lookup_id = user.employee_id or user.user_id
    db.query(DeviceToken).filter(
        DeviceToken.fcm_token == fcm_token,
        DeviceToken.employee_id == lookup_id,
    ).delete()
    db.commit()
    return {"ok": True}