from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.shift import ShiftAssignment
from app.core.database import SessionLocal
import logging
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def update_shift_statuses():
    """Обновляет статусы смен на основе текущего времени (Москва UTC+3)"""
    
    db = SessionLocal()
    try:
        # Получаем текущее московское время
        now_utc = datetime.utcnow()
        now_msk = now_utc + timedelta(hours=3)
        today_msk = now_msk.date()
        
        logger.info(f"🕐 Обновление статусов смен. Текущее время (МСК): {now_msk.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 1. Смены, которые должны начаться (статус scheduled -> in_progress)
        # Начало смены <= текущее время
        scheduled_shifts = db.query(ShiftAssignment).filter(
            ShiftAssignment.status == 'scheduled',
            ShiftAssignment.planned_start <= now_utc
        ).all()
        
        for shift in scheduled_shifts:
            # Пропускаем отпуск/больничный/отгул (у них статус уже другой)
            if shift.status in ['vacation', 'sick_leave', 'day_off']:
                continue
            shift.status = 'in_progress'
            logger.info(f"   ✅ Смена {shift.id} на {shift.shift_date} переведена в статус 'in_progress'")
        
        # 2. Смены, которые должны завершиться (статус in_progress -> completed)
        # Конец смены <= текущее время
        in_progress_shifts = db.query(ShiftAssignment).filter(
            ShiftAssignment.status == 'in_progress',
            ShiftAssignment.planned_end <= now_utc
        ).all()
        
        for shift in in_progress_shifts:
            shift.status = 'completed'
            logger.info(f"   ✅ Смена {shift.id} на {shift.shift_date} переведена в статус 'completed'")
        
        db.commit()
        
        total_updated = len(scheduled_shifts) + len(in_progress_shifts)
        if total_updated > 0:
            logger.info(f"📊 Обновлено смен: {total_updated} (началось: {len(scheduled_shifts)}, завершилось: {len(in_progress_shifts)})")
        else:
            logger.info("📊 Нет смен для обновления")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении статусов смен: {e}")
        db.rollback()
    finally:
        db.close()


async def run_shift_status_updater():
    """Запускает периодическое обновление статусов смен (каждые 5 минут)"""
    
    logger.info("🚀 Запущен планировщик обновления статусов смен")
    
    while True:
        try:
            update_shift_statuses()
        except Exception as e:
            logger.error(f"Ошибка в планировщике: {e}")
        
        # Ждём 5 минут перед следующим запуском
        await asyncio.sleep(300)  # 300 секунд = 5 минут