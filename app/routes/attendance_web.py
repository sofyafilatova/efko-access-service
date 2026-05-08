from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from uuid import UUID

from app.core.database import get_db

router = APIRouter(prefix="/web/attendance", tags=["Web - Attendance"])

@router.get("/employee-logs/{employee_id}")
def get_employee_attendance_logs(
    employee_id: UUID,
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    # Прямой SQL — никаких моделей
    query = text("""
        SELECT 
            ar.id,
            ar.employee_id,
            ar.event_at,
            ar.event_type,
            ar.source,
            ar.deny_reason,
            ar.credential_id,
            ap.name as access_point_name,
            z.name as zone_name
        FROM attendance_records ar
        LEFT JOIN access_points ap ON ar.access_point_id = ap.id
        LEFT JOIN zones z ON ap.zone_id = z.id
        WHERE ar.employee_id = :employee_id
        ORDER BY ar.event_at DESC
        LIMIT :limit OFFSET :offset
    """)
    
    rows = db.execute(query, {"employee_id": employee_id, "limit": limit, "offset": offset}).fetchall()
    
    total = db.execute(
        text("SELECT COUNT(*) FROM attendance_records WHERE employee_id = :employee_id"),
        {"employee_id": employee_id}
    ).scalar()
    
    items = []
    for row in rows:
        items.append({
            "id": str(row[0]),
            "employee_id": str(row[1]),
            "event_at": row[2].isoformat() if row[2] else None,
            "event_type": row[3],
            "source": row[4],
            "deny_reason": row[5],
            "credential_id": row[6],
            "access_point_name": row[7] or "Неизвестный турникет",
            "zone_name": row[8] or "Неизвестная зона"
        })
    
    return {"total": total, "items": items}