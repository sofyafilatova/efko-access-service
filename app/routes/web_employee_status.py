from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

from app.core.database import get_db
from app.models.employee import EmployeeView
from app.models.notification import Notification

router = APIRouter(prefix="/web/employee", tags=["Web - Employee Management"])

class StatusUpdateRequest(BaseModel):
    employee_id: UUID
    new_status: str  # "active" или "inactive"
    reason: str
    changed_by_user_id: UUID

@router.patch("/status")
def change_employee_status(
    data: StatusUpdateRequest,
    db: Session = Depends(get_db),
):
    """Изменить статус сотрудника (активен/заблокирован) и отправить уведомление"""
    
    # Проверяем валидность статуса
    if data.new_status not in ["active", "inactive"]:
        raise HTTPException(status_code=400, detail="Invalid status. Must be 'active' or 'inactive'")
    
    # Находим сотрудника
    employee = db.query(EmployeeView).filter(EmployeeView.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    old_status = employee.status
    
    # Обновляем статус (напрямую через update, т.к. EmployeeView может не поддерживать update)
    db.execute(
        f"UPDATE employees_view SET status = '{data.new_status}', updated_at = NOW() WHERE id = '{data.employee_id}'"
    )
    
    # Создаём уведомление
    if data.new_status == "inactive":
        title = "❌ Доступ заблокирован"
        body = f"Ваш доступ к системе заблокирован. Причина: {data.reason}"
    else:
        title = "✅ Доступ активирован"
        body = f"Ваш доступ к системе восстановлен. Причина: {data.reason}"
    
    notification = Notification(
        id=uuid.uuid4(),
        employee_id=data.employee_id,
        title=title,
        body=body,
        category="status_change",
        is_read=False,
        created_at=datetime.utcnow()
    )
    db.add(notification)
    db.commit()
    
    return {
        "message": f"Employee status changed from {old_status} to {data.new_status}",
        "employee_id": str(data.employee_id),
        "old_status": old_status,
        "new_status": data.new_status,
        "reason": data.reason
    }

@router.get("/positions")
def get_all_positions(
    db: Session = Depends(get_db),
):
    """Получить список всех должностей для фильтрации"""
    from app.models.employee import PositionView
    
    positions = db.query(PositionView.id, PositionView.title).order_by(PositionView.title).all()
    return [
        {
            "id": str(p.id),
            "name": p.title
        }
        for p in positions
    ]