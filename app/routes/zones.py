from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID
import uuid

from app.core.database import get_db
from app.models.zone import Zone
from app.schemas.zone import ZoneCreate, ZoneUpdate, ZoneRead
from app.models.zone import AccessPoint

router = APIRouter(prefix="/zones", tags=["Zones"])


@router.get("/", response_model=list[ZoneRead])
def get_zones(
    is_active: bool = Query(True),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    zones = db.query(Zone).filter(Zone.is_active == is_active).offset(offset).limit(limit).all()
    return zones


@router.get("/{zone_id}", response_model=ZoneRead)
def get_zone(
    zone_id: UUID,
    db: Session = Depends(get_db),
):
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    return zone


@router.post("/", response_model=ZoneRead, status_code=201)
def create_zone(
    data: ZoneCreate,
    db: Session = Depends(get_db),
):
    existing = db.query(Zone).filter(Zone.code == data.code).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Zone with code '{data.code}' already exists")

    zone = Zone(
        id=uuid.uuid4(),
        name=data.name,
        code=data.code,
        address=data.address,
        access_level=data.access_level,
        parent_zone_id=data.parent_zone_id,
        is_active=True
    )
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


@router.patch("/{zone_id}", response_model=ZoneRead)
def update_zone(
    zone_id: UUID,
    data: ZoneUpdate,
    db: Session = Depends(get_db),
):
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(zone, field, value)

    db.commit()
    db.refresh(zone)
    return zone


@router.delete("/{zone_id}", status_code=204)
def delete_zone(
    zone_id: UUID,
    db: Session = Depends(get_db),
):
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    zone.is_active = False
    db.commit()
    return None


@router.get("/{zone_id}/access-points")
def get_zone_access_points(
    zone_id: UUID,
    db: Session = Depends(get_db),
):
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    points = db.query(AccessPoint).filter(
        AccessPoint.zone_id == zone_id,
        AccessPoint.is_active == True
    ).all()

    return [
        {
            "id": str(p.id),
            "name": p.name,
            "type": p.type,
            "direction": p.direction,
        }
        for p in points
    ]