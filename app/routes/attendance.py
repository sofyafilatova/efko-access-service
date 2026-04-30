from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import date, datetime, timedelta

from app.core.database import get_db
from app.core.security import AnyEmployee, ShiftManagerPlus, AdminOnly, CurrentUser
from app.models.shift import AttendanceRecord
from app.schemas.attendance import CheckInRequest, CheckInResponse, AttendanceRecordRead
from app.services.attendance_service import process_check_in

router = APIRouter(prefix="/attendance", tags=["Attendance"])


@router.post("/check-in", response_model=CheckInResponse)
def check_in(
    data: CheckInRequest,
    db: Session = Depends(get_db),
    _: CurrentUser = AdminOnly   # вызывается от системы / турникета
):
    """
    Главный эндпоинт: фиксация прохода через турникет.
    Вызывается СКУД-контроллером или мобильным приложением при сканировании QR.
    """
    result = process_check_in(
        db=db,
        token_value=data.token_value,
        access_point_id=data.access_point_id,
        source=data.source,
        event_at=data.event_at,
    )
    return result


@router.get("/history", response_model=list[AttendanceRecordRead])
def get_history(
    employee_id: UUID | None = None,
    start_date: date = Query(default=None),
    end_date: date = Query(default=None),
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    """История проходов. Сотрудник видит только свои."""
    q = db.query(AttendanceRecord)

    # Сотрудник видит только своё
    if user.role == "EMPLOYEE":
        q = q.filter(AttendanceRecord.employee_id == user.user_id)
    elif employee_id:
        q = q.filter(AttendanceRecord.employee_id == employee_id)

    if start_date:
        q = q.filter(AttendanceRecord.event_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        q = q.filter(AttendanceRecord.event_at <= datetime.combine(end_date, datetime.max.time()))

    return (
        q.order_by(AttendanceRecord.event_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/today", response_model=list[AttendanceRecordRead])
def today_attendance(
    zone_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: CurrentUser = ShiftManagerPlus
):
    """Кто пришёл сегодня — для веб-админки раздел Смены."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    q = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.event_at >= today_start,
            AttendanceRecord.event_type == "granted",
        )
    )
    return q.order_by(AttendanceRecord.event_at.desc()).all() 
