from sqlalchemy.orm import Session
from uuid import UUID, uuid4
from datetime import datetime

from app.models.notification import Notification, DeviceToken


def create_notification(
    db: Session,
    employee_id: UUID,
    title: str,
    body: str,
    category: str = "system",
) -> Notification:
    """Создаём запись в БД. Push отправляется отдельно через FCM."""
    notif = Notification(
        id=uuid4(),
        employee_id=employee_id,
        title=title,
        body=body,
        category=category,
        is_read=False,
        created_at=datetime.utcnow(),
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


def get_device_tokens(db: Session, employee_id: UUID) -> list[DeviceToken]:
    return db.query(DeviceToken).filter(
        DeviceToken.employee_id == employee_id
    ).all()