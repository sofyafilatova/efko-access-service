from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID, uuid4
from datetime import datetime
from pydantic import BaseModel

from app.core.database import get_db
from app.models.employee import EmployeeView
from app.models.notification import Notification

router = APIRouter(prefix="/web/employee", tags=["Web - Employee Management"])

class StatusUpdateRequest(BaseModel):
    employee_id: UUID
    new_status: str
    reason: str
    changed_by_user_id: UUID

@router.put("/status")
def change_employee_status(
    data: StatusUpdateRequest,
    db: Session = Depends(get_db),
):
    """Изменить статус сотрудника (активен/заблокирован)"""
    
    print(f"🔧 Запрос на изменение статуса: {data.dict()}")
    
    if data.new_status not in ["active", "inactive"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    # Находим сотрудника
    employee = db.query(EmployeeView).filter(EmployeeView.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    old_status = employee.status
    
    # Обновляем статус через сырой SQL (так как EmployeeView - это view)
    try:
        db.execute(
            f"UPDATE employees_view SET status = '{data.new_status}' WHERE id = '{data.employee_id}'"
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"DB error: {str(e)}")
    
    # Создаём уведомление
    title = "❌ Доступ заблокирован" if data.new_status == "inactive" else "✅ Доступ активирован"
    body = f"Ваш доступ { 'заблокирован' if data.new_status == 'inactive' else 'восстановлен' }. Причина: {data.reason}"
    
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
        "message": f"Status changed: {old_status} → {data.new_status}",
        "employee_id": str(data.employee_id),
        "old_status": old_status,
        "new_status": data.new_status,
        "reason": data.reason
    }

@router.get("/positions")
def get_all_positions(db: Session = Depends(get_db)):
    """Список должностей (если понадобится)"""
    from app.models.employee import PositionView
    positions = db.query(PositionView.id, PositionView.title).order_by(PositionView.title).all()
    return [{"id": str(p.id), "name": p.title} for p in positions]