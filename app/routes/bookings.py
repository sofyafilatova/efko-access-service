from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_
from uuid import UUID, uuid4
from datetime import datetime

from app.core.database import get_db
from app.core.security import AnyEmployee, CurrentUser
from app.models.booking import Booking, BookableResource
from app.models.zone import Zone
from app.schemas.booking import BookingCreate, BookingRead, ResourceRead, QRResponse
from app.services.qr_service import issue_personal_qr, issue_booking_qr

router = APIRouter(tags=["Bookings"])


# ─── Ресурсы (рабочие места, переговорки) ────────────────────────────────────

@router.get("/resources", response_model=list[ResourceRead])
def list_resources(
    zone_id: UUID | None = None,
    type: str | None = None,
    floor: int | None = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    _: CurrentUser = AnyEmployee
):
    """Каталог мест для бронирования."""
    q = db.query(BookableResource).filter(BookableResource.is_active == True)
    if zone_id:
        q = q.filter(BookableResource.zone_id == zone_id)
    if type:
        q = q.filter(BookableResource.type == type)
    if floor is not None:
        q = q.filter(BookableResource.floor == floor)
    return q.limit(limit).all()


@router.get("/resources/{resource_id}/availability")
def resource_availability(
    resource_id: UUID,
    start: datetime = Query(...),
    end: datetime = Query(...),
    db: Session = Depends(get_db),
    _: CurrentUser = AnyEmployee
):
    """Свободен ли ресурс в указанный период."""
    resource = db.query(BookableResource).filter(BookableResource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    overlap = (
        db.query(Booking)
        .filter(
            Booking.resource_id == resource_id,
            Booking.status == "active",
            Booking.start_at < end,
            Booking.end_at > start,
        )
        .first()
    )
    return {
        "resource_id": resource_id,
        "start": start,
        "end": end,
        "is_available": overlap is None,
        "conflicting_booking_id": str(overlap.id) if overlap else None,
    }


# ─── Брони ────────────────────────────────────────────────────────────────────

@router.get("/bookings", response_model=list[BookingRead])
def list_bookings(
    status: str | None = "active",
    limit: int = Query(20, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    """Мои брони. Сотрудник видит только свои."""
    lookup_id = user.employee_id or user.user_id
    q = db.query(Booking).filter(Booking.employee_id == lookup_id)
    if status:
        q = q.filter(Booking.status == status)
    return q.order_by(Booking.start_at.desc()).offset(offset).limit(limit).all()


@router.get("/bookings/active", response_model=list[BookingRead])
def active_bookings(
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    """Активные брони — главный экран мобилки."""
    lookup_id = user.employee_id or user.user_id
    now = datetime.utcnow()
    return (
        db.query(Booking)
        .filter(
            Booking.employee_id == lookup_id,
            Booking.status == "active",
            Booking.end_at >= now,
        )
        .order_by(Booking.start_at)
        .all()
    )


@router.post("/bookings", response_model=BookingRead, status_code=201)
def create_booking(
    data: BookingCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    """Создать бронь. Проверяет конфликт по времени."""
    lookup_id = user.employee_id or user.user_id
    resource = db.query(BookableResource).filter(
        BookableResource.id == data.resource_id,
        BookableResource.is_active == True
    ).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found or inactive")

    # Проверка конфликта
    overlap = (
        db.query(Booking)
        .filter(
            Booking.resource_id == data.resource_id,
            Booking.status == "active",
            Booking.start_at < data.end_at,
            Booking.end_at > data.start_at,
        )
        .first()
    )
    if overlap:
        raise HTTPException(
            status_code=409,
            detail=f"Resource already booked from {overlap.start_at} to {overlap.end_at}"
        )

    booking = Booking(
        id=uuid4(),
        employee_id=lookup_id,
        resource_id=data.resource_id,
        start_at=data.start_at,
        end_at=data.end_at,
        status="active",
        created_at=datetime.utcnow(),
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@router.delete("/bookings/{booking_id}", status_code=204)
def cancel_booking(
    booking_id: UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    """Отмена брони. Только своей."""
    lookup_id = user.employee_id or user.user_id
    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.employee_id == lookup_id,
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status != "active":
        raise HTTPException(status_code=409, detail="Booking is not active")

    booking.status = "cancelled"
    booking.cancelled_at = datetime.utcnow()

    # Отзываем QR брони
    from app.models.access import Credential
    db.query(Credential).filter(
        Credential.subject_type == "booking",
        Credential.subject_id == booking_id,
    ).update({"is_revoked": True})

    db.commit()


@router.get("/bookings/{booking_id}/qr", response_model=QRResponse)
def booking_qr(
    booking_id: UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    """QR-код для прохода к забронированному месту."""
    lookup_id = user.employee_id or user.user_id
    booking = db.query(Booking).filter(
        Booking.id == booking_id,
        Booking.employee_id == lookup_id,
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status != "active":
        raise HTTPException(status_code=409, detail="Booking is not active")

    cred = issue_booking_qr(db, booking_id, lookup_id)
    return QRResponse(
        credential_id=cred.id,
        token_value=cred.token_value,
        expires_at=cred.expires_at,
        qr_data=cred.token_value,
    )


# ─── Личный QR пропуск ────────────────────────────────────────────────────────

@router.get("/my/qr", response_model=QRResponse)
def my_personal_qr(
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    """
    Личный QR-пропуск сотрудника. Живёт 60 секунд.
    Каждый вызов — новый токен, старый отзывается.
    """
    lookup_id = user.employee_id or user.user_id
    cred = issue_personal_qr(db, lookup_id, ttl_seconds=60)
    return QRResponse(
        credential_id=cred.id,
        token_value=cred.token_value,
        expires_at=cred.expires_at,
        qr_data=cred.token_value,
    )