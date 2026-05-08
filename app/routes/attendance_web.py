from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from uuid import UUID, uuid4
from datetime import datetime
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.models.access import AccessRight
from app.models.attendance import AttendanceRecord
from app.models.access_point import AccessPoint
from app.models.zone import Zone
from app.models.employee import EmployeeView
from app.models.notification import Notification

router = APIRouter(prefix="/web/attendance", tags=["Web - Attendance"])

class AccessAttempt(BaseModel):
    employee_id: UUID
    access_point_id: UUID
    credential_id: Optional[str] = None

@router.post("/check-access")
def check_access_and_log(
    data: AccessAttempt,
    db: Session = Depends(get_db),
):
    """Проверяет доступ сотрудника к зоне через турникет и записывает лог"""
    
    # Получаем информацию о турникете и зоне
    access_point = db.query(AccessPoint).filter(AccessPoint.id == data.access_point_id).first()
    if not access_point:
        raise HTTPException(status_code=404, detail="Access point not found")
    
    zone = db.query(Zone).filter(Zone.id == access_point.zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    
    # Получаем информацию о сотруднике
    employee = db.query(EmployeeView).filter(EmployeeView.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Проверяем права доступа сотрудника
    access_right = db.query(AccessRight).filter(
        AccessRight.employee_id == data.employee_id,
        AccessRight.zone_id == zone.id
    ).first()
    
    # Определяем, разрешён ли доступ
    is_allowed = access_right and access_right.is_permitted and employee.status == 'active'
    
    # Создаём запись в attendance_records
    attendance_record = AttendanceRecord(
        id=uuid4(),
        employee_id=data.employee_id,
        shift_assignment_id=None,  # Пока не привязываем к смене
        access_point_id=data.access_point_id,
        event_at=datetime.utcnow(),
        event_type="granted" if is_allowed else "denied",
        source="turnstile",
        deny_reason=None if is_allowed else f"Нет доступа в зону: {zone.name}",
        credential_id=data.credential_id
    )
    db.add(attendance_record)
    db.commit()
    
    # Если доступ запрещён и сотрудник активен, создаём уведомление для HR
    if not is_allowed and employee.status == 'active':
        notification = Notification(
            id=uuid4(),
            employee_id=data.employee_id,
            title="⚠️ Нарушение доступа",
            body=f"Сотрудник {employee.full_name} попытался пройти через {access_point.name} в зону {zone.name}. Доступ запрещён.",
            category="access_violation",
            is_read=False,
            created_at=datetime.utcnow()
        )
        db.add(notification)
        db.commit()
    
    return {
        "allowed": is_allowed,
        "message": "Доступ разрешён" if is_allowed else "Доступ запрещён",
        "attendance_record_id": str(attendance_record.id),
        "employee_name": employee.full_name,
        "zone_name": zone.name,
        "access_point_name": access_point.name,
        "timestamp": attendance_record.event_at.isoformat()
    }

@router.get("/employee-logs/{employee_id}")
def get_employee_attendance_logs(
    employee_id: UUID,
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    """Получить все логи проходов сотрудника"""
    
    logs = db.query(AttendanceRecord).filter(
        AttendanceRecord.employee_id == employee_id
    ).order_by(AttendanceRecord.event_at.desc()).offset(offset).limit(limit).all()
    
    # Обогащаем данными о турникетах и зонах
    result = []
    for log in logs:
        access_point = db.query(AccessPoint).filter(AccessPoint.id == log.access_point_id).first()
        zone = db.query(Zone).filter(Zone.id == access_point.zone_id).first() if access_point else None
        
        result.append({
            "id": str(log.id),
            "employee_id": str(log.employee_id),
            "access_point_name": access_point.name if access_point else "Неизвестный турникет",
            "zone_name": zone.name if zone else "Неизвестная зона",
            "event_at": log.event_at.isoformat(),
            "event_type": log.event_type,
            "source": log.source,
            "deny_reason": log.deny_reason,
            "credential_id": log.credential_id
        })
    
    total = db.query(AttendanceRecord).filter(AttendanceRecord.employee_id == employee_id).count()
    
    return {
        "total": total,
        "items": result
    }