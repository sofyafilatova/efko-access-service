from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from uuid import UUID, uuid4
from datetime import datetime
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.models.employee import EmployeeView
from app.models.notification import Notification

router = APIRouter(prefix="/web/employee", tags=["Web - Employee Management"])

class StatusUpdateRequest(BaseModel):
    employee_id: UUID
    new_status: str
    reason: str
    changed_by_user_id: Optional[UUID] = None  # ← Сделал опциональным

@router.put("/status")
def change_employee_status(
    data: StatusUpdateRequest,
    db: Session = Depends(get_db),
):
    """Изменить статус сотрудника (активен/заблокирован)"""
    
    print(f"🔧 Запрос на изменение статуса: {data.dict()}")
    
    # Разрешаем как inactive, так и terminated (оба варианта)
    if data.new_status not in ["active", "inactive", "terminated"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    # Нормализуем статус: если пришло terminated, сохраняем как есть
    final_status = data.new_status
    
    # Находим сотрудника
    employee = db.query(EmployeeView).filter(EmployeeView.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    old_status = employee.status
    
    # Обновляем статус через сырой SQL с text()
    try:
        db.execute(
            text(f"UPDATE employees_view SET status = '{final_status}' WHERE id = '{data.employee_id}'")
        )
        db.commit()
        print(f"✅ Статус обновлён: {old_status} → {final_status}")
    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка БД: {e}")
        raise HTTPException(status_code=500, detail=f"DB error: {str(e)}")
    
    # Создаём уведомление
    if final_status in ["inactive", "terminated"]:
        title = "❌ Доступ заблокирован"
        body = f"Ваш доступ к системе заблокирован. Причина: {data.reason}"
    else:
        title = "✅ Доступ активирован"
        body = f"Ваш доступ к системе восстановлен. Причина: {data.reason}"
    
    notification = Notification(
        id=uuid4(),
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
        "message": f"Employee status changed from {old_status} to {final_status}",
        "employee_id": str(data.employee_id),
        "old_status": old_status,
        "new_status": final_status,
        "reason": data.reason
    }


@router.get("/positions")
def get_all_positions(db: Session = Depends(get_db)):
    """Список всех должностей для фильтрации"""
    from app.models.employee import PositionView
    
    positions = db.query(PositionView.id, PositionView.title).order_by(PositionView.title).all()
    return [
        {
            "id": str(p.id),
            "name": p.title
        }
        for p in positions
    ]