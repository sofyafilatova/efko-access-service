from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID, uuid4
from datetime import datetime

from app.core.database import get_db
from app.core.security import AnyEmployee, AdminOnly, ShiftManagerPlus, CurrentUser
from app.models.notification import GuestPass
from app.models.zone import Zone
from app.schemas.guest_pass import GuestPassCreate, GuestPassRead
from app.services.qr_service import issue_guest_qr
from app.schemas.booking import QRResponse

router = APIRouter(prefix="/guest-passes", tags=["Guest Passes"], redirect_slashes=False)


@router.post("/", response_model=GuestPassRead, status_code=201)
def create_guest_pass(
    data: GuestPassCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    if data.valid_until <= data.valid_from:
        raise HTTPException(status_code=400, detail="valid_until must be after valid_from")

    for zone_id in data.zone_ids:
        zone = db.query(Zone).filter(Zone.id == zone_id, Zone.is_active == True).first()
        if not zone:
            raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")

    # ИСПРАВЛЕНИЕ: используем employee_id из токена, не user_id
    invited_by = user.employee_id or user.user_id

    guest_pass = GuestPass(
        id=uuid4(),
        invited_by_employee_id=invited_by,
        guest_full_name=data.guest_full_name,
        guest_phone=data.guest_phone,
        guest_company=data.guest_company,
        visit_purpose=data.visit_purpose,
        valid_from=data.valid_from,
        valid_until=data.valid_until,
        status="pending",
    )
    db.add(guest_pass)
    db.flush()

    for zone_id in data.zone_ids:
        db.execute(
            __import__('sqlalchemy').text(
                "INSERT INTO guest_pass_zones (pass_id, zone_id) VALUES (:pass_id, :zone_id)"
            ),
            {"pass_id": str(guest_pass.id), "zone_id": str(zone_id)}
        )

    db.commit()
    db.refresh(guest_pass)
    return guest_pass


@router.get("/", response_model=list[GuestPassRead])
def list_guest_passes(
    status: str | None = None,
    limit: int = Query(20, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: CurrentUser = ShiftManagerPlus
):
    q = db.query(GuestPass)
    if status:
        q = q.filter(GuestPass.status == status)
    return q.order_by(GuestPass.valid_from.desc()).offset(offset).limit(limit).all()


@router.get("/{pass_id}", response_model=GuestPassRead)
def get_guest_pass(
    pass_id: UUID,
    db: Session = Depends(get_db),
    _: CurrentUser = AnyEmployee
):
    gp = db.query(GuestPass).filter(GuestPass.id == pass_id).first()
    if not gp:
        raise HTTPException(status_code=404, detail="Guest pass not found")
    return gp


@router.patch("/{pass_id}/approve", response_model=GuestPassRead)
def approve_guest_pass(
    pass_id: UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = AdminOnly
):
    """Охрана/администратор одобряет гостевой пропуск."""
    gp = db.query(GuestPass).filter(GuestPass.id == pass_id).first()
    if not gp:
        raise HTTPException(status_code=404, detail="Guest pass not found")
    if gp.status != "pending":
        raise HTTPException(status_code=409, detail=f"Cannot approve pass with status '{gp.status}'")

    gp.status = "active"
    gp.approved_by_user_id = user.user_id
    db.commit()
    db.refresh(gp)
    return gp


@router.patch("/{pass_id}/revoke", response_model=GuestPassRead)
def revoke_guest_pass(
    pass_id: UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = AdminOnly
):
    """Отозвать гостевой пропуск досрочно."""
    gp = db.query(GuestPass).filter(GuestPass.id == pass_id).first()
    if not gp:
        raise HTTPException(status_code=404, detail="Guest pass not found")
    if gp.status not in ("pending", "active"):
        raise HTTPException(status_code=409, detail="Pass already revoked or expired")

    gp.status = "revoked"

    # Отзываем QR
    from app.models.access import Credential
    db.query(Credential).filter(
        Credential.subject_type == "guest_pass",
        Credential.subject_id == pass_id,
    ).update({"is_revoked": True})

    db.commit()
    db.refresh(gp)
    return gp


@router.get("/{pass_id}/qr", response_model=QRResponse)
def guest_pass_qr(
    pass_id: UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    """QR для гостя — отправить гостю для прохода."""
    gp = db.query(GuestPass).filter(GuestPass.id == pass_id).first()
    if not gp:
        raise HTTPException(status_code=404, detail="Guest pass not found")
    if gp.status != "active":
        raise HTTPException(status_code=409, detail="Guest pass is not active")
    if gp.invited_by_employee_id != user.user_id:
        raise HTTPException(status_code=403, detail="Not your guest pass")

    cred = issue_guest_qr(db, pass_id)
    return QRResponse(
        credential_id=cred.id,
        token_value=cred.token_value,
        expires_at=cred.expires_at,
        qr_data=cred.token_value,
    )