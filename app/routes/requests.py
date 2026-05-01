from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID, uuid4
from datetime import datetime

from app.core.database import get_db
from app.core.security import AnyEmployee, ShiftManagerPlus, CurrentUser
from app.models.notification import Request, Notification
from app.schemas.request import RequestCreate, RequestRead, RequestApprove, RequestReject
from app.services.notification_service import create_notification

router = APIRouter(prefix="/requests", tags=["Requests"])

VALID_TYPES = {"shift_change", "profile_change", "extend_shift", "additional_access"}


@router.post("/", response_model=RequestRead, status_code=201)
def create_request(
    data: RequestCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    lookup_id = user.employee_id or user.user_id
    if data.type not in VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid type. Must be one of: {VALID_TYPES}"
        )

    req = Request(
        id=uuid4(),
        employee_id=lookup_id,  # ← было user.user_id
        type=data.type,
        status="pending",
        payload=data.payload,
        created_at=datetime.utcnow(),
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req 

@router.get("/my", response_model=list[RequestRead])
def my_requests(
    status: str | None = None,
    limit: int = Query(20, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: CurrentUser = AnyEmployee
):
    lookup_id = user.employee_id or user.user_id
    q = db.query(Request).filter(Request.employee_id == lookup_id)
    if status:
        q = q.filter(Request.status == status)
    return q.order_by(Request.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/", response_model=list[RequestRead])
def list_requests(
    status: str | None = "pending",
    type: str | None = None,
    employee_id: UUID | None = None,
    limit: int = Query(20, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
    _: CurrentUser = ShiftManagerPlus
):
    """Все запросы — для веб-админки."""
    q = db.query(Request)
    if status:
        q = q.filter(Request.status == status)
    if type:
        q = q.filter(Request.type == type)
    if employee_id:
        q = q.filter(Request.employee_id == employee_id)
    return q.order_by(Request.created_at.desc()).offset(offset).limit(limit).all()


@router.patch("/{request_id}/approve", response_model=RequestRead)
def approve_request(
    request_id: UUID,
    data: RequestApprove,
    db: Session = Depends(get_db),
    user: CurrentUser = ShiftManagerPlus
):
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=409, detail=f"Request already {req.status}")

    req.status = "approved"
    req.admin_comment = data.admin_comment
    req.processed_by_user_id = user.user_id
    req.processed_at = datetime.utcnow()

    # Применяем изменение профиля автоматически
    if req.type == "profile_change":
        _apply_profile_change(db, req.employee_id, req.payload)

    db.commit()
    db.refresh(req)

    # Уведомляем сотрудника
    create_notification(
        db,
        employee_id=req.employee_id,
        title="Запрос одобрен",
        body=f"Ваш запрос «{req.type}» был одобрен.",
        category="request",
    )

    return req


@router.patch("/{request_id}/reject", response_model=RequestRead)
def reject_request(
    request_id: UUID,
    data: RequestReject,
    db: Session = Depends(get_db),
    user: CurrentUser = ShiftManagerPlus
):
    req = db.query(Request).filter(Request.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=409, detail=f"Request already {req.status}")

    req.status = "rejected"
    req.admin_comment = data.admin_comment
    req.processed_by_user_id = user.user_id
    req.processed_at = datetime.utcnow()
    db.commit()
    db.refresh(req)

    create_notification(
        db,
        employee_id=req.employee_id,
        title="Запрос отклонён",
        body=f"Ваш запрос «{req.type}» отклонён. Причина: {data.admin_comment}",
        category="request",
    )

    return req


def _apply_profile_change(db: Session, employee_id: UUID, payload: dict):
    from app.models.employee import EmployeeProfile
    profile = db.query(EmployeeProfile).filter(
        EmployeeProfile.employee_id == employee_id
    ).first()
    if not profile:
        return
    allowed = {"first_name", "last_name", "patronymic", "phone"}
    for field, value in payload.items():
        if field in allowed:
            setattr(profile, field, value)