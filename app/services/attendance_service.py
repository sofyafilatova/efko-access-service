from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from app.models.shift import ShiftAssignment, AttendanceRecord
from app.models.zone import AccessPoint, Zone
from app.models.access import Credential, AccessRight
from app.models.employee import EmployeeView


def process_check_in(
    db: Session,
    token_value: str,
    access_point_id: UUID,
    source: str,
    event_at: datetime | None = None,
) -> dict:
    """
    Главный сценарий: кто-то приложил карту / показал QR.
    1. Найти credential по token_value
    2. Проверить что не отозван и не истёк
    3. Найти сотрудника
    4. Проверить права на зону точки прохода
    5. Зафиксировать attendance_record
    6. Вернуть result: granted / denied
    """
    now = event_at or datetime.utcnow()

    # Шаг 1 — найти credential
    credential = (
        db.query(Credential)
        .filter(Credential.token_value == token_value)
        .first()
    )

    if not credential:
        return _denied("CREDENTIAL_NOT_FOUND", access_point_id, None, None, db, now, source)

    # Шаг 2 — проверить статус
    if credential.is_revoked:
        return _denied("CREDENTIAL_REVOKED", access_point_id, None, credential.id, db, now, source)

    if credential.expires_at and credential.expires_at < now:
        return _denied("CREDENTIAL_EXPIRED", access_point_id, None, credential.id, db, now, source)

    # Шаг 3 — найти сотрудника через тип credential
    if credential.subject_type == "personal":
        employee_id = credential.subject_id

    elif credential.subject_type == "booking":
        from app.models.booking import Booking
        booking = db.query(Booking).filter(Booking.id == credential.subject_id).first()
        if not booking:
            return _denied("BOOKING_NOT_FOUND", access_point_id, None, credential.id, db, now, source)
        if booking.status != "active":
            return _denied("BOOKING_CANCELLED", access_point_id, None, credential.id, db, now, source)
        employee_id = booking.employee_id

    elif credential.subject_type == "guest_pass":
        from app.models.notification import GuestPass
        guest_pass = db.query(GuestPass).filter(GuestPass.id == credential.subject_id).first()
        if not guest_pass:
            return _denied("GUEST_PASS_NOT_FOUND", access_point_id, None, credential.id, db, now, source)
        if guest_pass.status not in ("active",):
            return _denied("GUEST_PASS_INACTIVE", access_point_id, None, credential.id, db, now, source)
        # Гость не сотрудник — пускаем без employee_id
        record = AttendanceRecord(
            id=uuid4(),
            employee_id=None,
            shift_assignment_id=None,
            access_point_id=access_point_id,
            event_at=now,
            event_type="granted",
            source=source,
            credential_id=credential.id,
        )
        db.add(record)
        db.commit()
        return {
            "result": "granted",
            "employee_id": None,
            "employee_name": guest_pass.guest_full_name,
            "shift_id": None,
            "deny_reason": None,
        }

    else:
        return _denied("UNKNOWN_CREDENTIAL_TYPE", access_point_id, None, credential.id, db, now, source)

    # Шаг 4 — проверить, что сотрудник активен
    employee = db.query(EmployeeView).filter(EmployeeView.id == employee_id).first()
    if not employee or employee.status != "active":
        return _denied("EMPLOYEE_INACTIVE", access_point_id, employee_id, credential.id, db, now, source)

    # Шаг 5 — проверить права на зону
    access_point = db.query(AccessPoint).filter(AccessPoint.id == access_point_id).first()
    if not access_point:
        return _denied("ACCESS_POINT_NOT_FOUND", access_point_id, employee_id, credential.id, db, now, source)

    access_right = (
        db.query(AccessRight)
        .filter(
            AccessRight.employee_id == employee_id,
            AccessRight.zone_id == access_point.zone_id,
            AccessRight.is_permitted == True,
        )
        .first()
    )

    # public зона — пускаем без права
    zone = db.query(Zone).filter(Zone.id == access_point.zone_id).first()
    has_access = (zone and zone.access_level == "public") or (
        access_right is not None and
        (access_right.expires_at is None or access_right.expires_at > now)
    )

    if not has_access:
        return _denied("NO_ZONE_ACCESS", access_point_id, employee_id, credential.id, db, now, source)

    # Шаг 6 — найти активную смену
    shift = (
        db.query(ShiftAssignment)
        .filter(
            ShiftAssignment.employee_id == employee_id,
            ShiftAssignment.planned_start <= now,
            ShiftAssignment.planned_end >= now,
        )
        .first()
    )

    # Фиксируем проход
    record = AttendanceRecord(
        id=uuid4(),
        employee_id=employee_id,
        shift_assignment_id=shift.id if shift else None,
        access_point_id=access_point_id,
        event_at=now,
        event_type="granted",
        source=source,
        credential_id=credential.id,
    )
    db.add(record)

    # Обновляем статус смены
    if shift and shift.status == "scheduled":
        shift.status = "in_progress"

    db.commit()

    # ========== ДОБАВЛЕННЫЙ БЛОК RABBITMQ ==========
    # Публикуем событие в RabbitMQ (fire-and-forget)
    import asyncio
    from app.core.rabbitmq import publish_event

    # Определяем тип события: вход или выход
    event_type = "access.attendance.checked_in"
    if access_point.direction == "exit":
        event_type = "access.attendance.checked_out"

    try:
        loop = asyncio.get_event_loop()
        loop.create_task(publish_event(event_type, {
            "employee_id": str(employee_id),
            "employee_name": employee.full_name,
            "access_point_id": str(access_point_id),
            "zone_id": str(access_point.zone_id),
            "shift_id": str(shift.id) if shift else None,
            "event_at": now.isoformat(),
        }))
    except Exception:
        pass  # события не должны ронять основной поток
    # ========== КОНЕЦ БЛОКА RABBITMQ ==========

    return {
        "result": "granted",
        "employee_id": employee_id,
        "employee_name": employee.full_name,
        "shift_id": shift.id if shift else None,
        "deny_reason": None,
    }


def _denied(
    reason: str,
    access_point_id: UUID,
    employee_id: UUID | None,
    credential_id: UUID | None,
    db: Session,
    now: datetime,
    source: str,
) -> dict:
    """Фиксируем отказ только если точка доступа реально существует."""
    if employee_id and reason != "ACCESS_POINT_NOT_FOUND":
        # Не пишем запись если точки нет — нарушит FK
        point_exists = db.query(AccessPoint).filter(
            AccessPoint.id == access_point_id
        ).first()

        if point_exists:
            record = AttendanceRecord(
                id=uuid4(),
                employee_id=employee_id,
                shift_assignment_id=None,
                access_point_id=access_point_id,
                event_at=now,
                event_type="denied",
                source=source,
                deny_reason=reason,
                credential_id=credential_id,
            )
            db.add(record)
            db.commit()

    return {
        "result": "denied",
        "employee_id": employee_id,
        "employee_name": None,
        "shift_id": None,
        "deny_reason": reason,
    }