from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID, uuid4
from datetime import datetime
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.models.notification import Notification

router = APIRouter(prefix="/web/notifications", tags=["Web - Notifications"])

class WebNotificationCreate(BaseModel):
    employee_id: UUID
    title: str
    body: str
    category: str = "hr_message"

@router.post("/")
def create_web_notification(
    data: WebNotificationCreate,
    db: Session = Depends(get_db),
):
    """Создать уведомление для сотрудника (без авторизации)"""
    
    # Создаём уведомление
    notification = Notification(
        id=uuid4(),
        employee_id=data.employee_id,
        title=data.title,
        body=data.body,
        category=data.category,
        is_read=False,
        created_at=datetime.utcnow()
    )
    db.add(notification)
    db.commit()
    
    return {
        "message": "Уведомление отправлено",
        "notification_id": str(notification.id),
        "employee_id": str(data.employee_id),
        "title": data.title,
        "body": data.body
    }