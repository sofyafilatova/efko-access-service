from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from uuid import UUID, uuid4
from datetime import datetime
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.security import CurrentUser, AnyEmployee, ShiftManagerPlus

router = APIRouter(prefix="/web/broadcasts", tags=["Web - Broadcasts"])

class BroadcastCreate(BaseModel):
    title: str
    body: str


@router.post("/")
def create_broadcast(
    data: BroadcastCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = ShiftManagerPlus
):
    """Создать массовую рассылку (только для HR/администраторов)"""
    
    query = text("""
        INSERT INTO broadcasts (id, title, body, created_at, created_by_user_id, is_active)
        VALUES (gen_random_uuid(), :title, :body, NOW(), :user_id, true)
        RETURNING id
    """)
    
    result = db.execute(query, {
        "title": data.title,
        "body": data.body,
        "user_id": user.user_id
    })
    db.commit()
    
    broadcast_id = result.fetchone()[0]
    
    return {
        "message": "Broadcast created successfully",
        "broadcast_id": str(broadcast_id),
        "title": data.title,
        "body": data.body,
        "created_at": datetime.utcnow().isoformat()
    }


@router.get("/")
def get_broadcasts(
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    # Убираем зависимость от пользователя для GET-запроса
):
    """Получить список всех рассылок (доступно всем, даже без авторизации)"""
    
    query = text("""
        SELECT id, title, body, created_at, created_by_user_id
        FROM broadcasts
        WHERE is_active = true
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    
    result = db.execute(query, {"limit": limit, "offset": offset})
    rows = result.fetchall()
    
    total_query = text("SELECT COUNT(*) FROM broadcasts WHERE is_active = true")
    total = db.execute(total_query).scalar()
    
    return {
        "total": total,
        "items": [
            {
                "id": str(row[0]),
                "title": row[1],
                "body": row[2],
                "created_at": row[3].isoformat() if row[3] else None,
                "created_by_user_id": str(row[4]) if row[4] else None
            }
            for row in rows
        ]
    }


@router.delete("/{broadcast_id}")
def delete_broadcast(
    broadcast_id: UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = ShiftManagerPlus
):
    """Удалить рассылку (деактивировать)"""
    
    query = text("""
        UPDATE broadcasts SET is_active = false
        WHERE id = :broadcast_id
    """)
    
    result = db.execute(query, {"broadcast_id": broadcast_id})
    db.commit()
    
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    
    return {"message": "Broadcast deleted successfully"}