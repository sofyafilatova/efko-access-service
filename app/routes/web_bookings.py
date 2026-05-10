from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date

from app.core.database import get_db

router = APIRouter(prefix="/web/bookings", tags=["Web - Bookings"])

@router.get("/stats")
def get_booking_stats(
    target_date: date = Query(..., description="Дата в формате YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """
    Статистика бронирований на указанную дату:
    - active_count: количество активных броней на эту дату
    - total_resources: общее количество ресурсов (bookable_resources)
    - utilization_percent: процент занятых ресурсов (уникальных) на дату
    - avg_load: среднее количество броней на ресурс
    """
    
    # 1. Активные бронирования на дату
    active_query = text("""
        SELECT COUNT(*)
        FROM bookings b
        WHERE DATE(b.start_at) = :target_date
          AND b.status = 'active'
    """)
    active_count = db.execute(active_query, {"target_date": target_date}).scalar() or 0
    
    # 2. Общее количество ресурсов
    total_resources_query = text("SELECT COUNT(*) FROM bookable_resources WHERE is_active = true")
    total_resources = db.execute(total_resources_query).scalar() or 0
    
    # 3. Количество уникальных ресурсов, занятых в этот день
    occupied_resources_query = text("""
        SELECT COUNT(DISTINCT b.resource_id)
        FROM bookings b
        WHERE DATE(b.start_at) = :target_date
          AND b.status = 'active'
    """)
    occupied_resources = db.execute(occupied_resources_query, {"target_date": target_date}).scalar() or 0
    
    utilization_percent = round((occupied_resources / total_resources) * 100) if total_resources > 0 else 0
    
    # 4. Средняя загрузка ресурса (общее бронирование / количество ресурсов)
    total_bookings_query = text("""
        SELECT COUNT(*)
        FROM bookings b
        WHERE DATE(b.start_at) = :target_date
          AND b.status = 'active'
    """)
    total_bookings = db.execute(total_bookings_query, {"target_date": target_date}).scalar() or 0
    
    avg_load = round(total_bookings / total_resources, 2) if total_resources > 0 else 0
    
    return {
        "active_count": active_count,
        "total_resources": total_resources,
        "occupied_resources": occupied_resources,
        "utilization_percent": utilization_percent,
        "total_bookings": total_bookings,
        "avg_load": avg_load,
        "target_date": target_date.isoformat()
    }