import hmac
import hashlib
import secrets
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from sqlalchemy.orm import Session

from app.models.access import Credential
from app.core.config import settings


def _sign_token(raw: str) -> str:
    """HMAC-SHA256 подпись. raw = 'type:subject_id:expires:nonce'"""
    return hmac.new(
        settings.jwt_secret_key.encode(),
        raw.encode(),
        hashlib.sha256
    ).hexdigest()[:32]


def issue_personal_qr(db: Session, employee_id: UUID, ttl_seconds: int = 60) -> Credential:
    """
    Выпускает личный QR для сотрудника.
    Старые личные QR этого сотрудника — отзываем.
    """
    # Отзываем предыдущие личные QR этого сотрудника
    old = (
        db.query(Credential)
        .filter(
            Credential.subject_type == "personal",
            Credential.subject_id == employee_id,
            Credential.medium == "qr",
            Credential.is_revoked == False,
        )
        .all()
    )
    for cred in old:
        cred.is_revoked = True

    expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    nonce = secrets.token_hex(8)
    raw = f"personal:{employee_id}:{expires_at.isoformat()}:{nonce}"
    token_value = _sign_token(raw)

    # Берём версию как max предыдущих + 1
    version = len(old) + 1

    cred = Credential(
        id=uuid4(),
        subject_type="personal",
        subject_id=employee_id,
        token_value=token_value,
        medium="qr",
        issued_at=datetime.utcnow(),
        expires_at=expires_at,
        version=version,
        is_revoked=False,
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return cred


def issue_booking_qr(db: Session, booking_id: UUID, employee_id: UUID) -> Credential:
    """QR для прохода к забронированному месту. Живёт до конца брони."""
    from app.models.booking import Booking
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise ValueError("Booking not found")

    # Отзываем предыдущий QR для этой брони
    old = (
        db.query(Credential)
        .filter(
            Credential.subject_type == "booking",
            Credential.subject_id == booking_id,
            Credential.is_revoked == False,
        )
        .all()
    )
    for cred in old:
        cred.is_revoked = True

    nonce = secrets.token_hex(8)
    raw = f"booking:{booking_id}:{booking.end_at.isoformat()}:{nonce}"
    token_value = _sign_token(raw)

    cred = Credential(
        id=uuid4(),
        subject_type="booking",
        subject_id=booking_id,
        token_value=token_value,
        medium="qr",
        issued_at=datetime.utcnow(),
        expires_at=booking.end_at,
        version=len(old) + 1,
        is_revoked=False,
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return cred


def issue_guest_qr(db: Session, pass_id: UUID) -> Credential:
    """QR для гостевого пропуска. Живёт до valid_until."""
    from app.models.notification import GuestPass
    guest_pass = db.query(GuestPass).filter(GuestPass.id == pass_id).first()
    if not guest_pass:
        raise ValueError("GuestPass not found")

    old = (
        db.query(Credential)
        .filter(
            Credential.subject_type == "guest_pass",
            Credential.subject_id == pass_id,
            Credential.is_revoked == False,
        )
        .all()
    )
    for cred in old:
        cred.is_revoked = True

    nonce = secrets.token_hex(8)
    raw = f"guest_pass:{pass_id}:{guest_pass.valid_until.isoformat()}:{nonce}"
    token_value = _sign_token(raw)

    cred = Credential(
        id=uuid4(),
        subject_type="guest_pass",
        subject_id=pass_id,
        token_value=token_value,
        medium="qr",
        issued_at=datetime.utcnow(),
        expires_at=guest_pass.valid_until,
        version=len(old) + 1,
        is_revoked=False,
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return cred