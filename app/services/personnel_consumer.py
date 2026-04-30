import aio_pika
import json
import logging
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.employee import EmployeeView, EmployeeProfile, DepartmentView, PositionView

logger = logging.getLogger(__name__)

PERSONNEL_EXCHANGE = "efko.personnel.events"
QUEUE_NAME = "access-service.personnel.events.queue"


async def start_personnel_consumer():
    """
    Слушает события из personnel-сервиса ядра.
    Запускается при старте приложения.
    """
    try:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)

        exchange = await channel.declare_exchange(
            PERSONNEL_EXCHANGE,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        queue = await channel.declare_queue(QUEUE_NAME, durable=True)

        # Подписываемся на все события personnel
        await queue.bind(exchange, routing_key="personnel.employee.*")
        await queue.bind(exchange, routing_key="personnel.department.*")
        await queue.bind(exchange, routing_key="personnel.position.*")

        logger.info(f"Personnel consumer started, queue: {QUEUE_NAME}")

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        await _handle_message(message)
                    except Exception as e:
                        logger.error(f"Error handling message: {e}")

    except Exception as e:
        logger.error(f"Personnel consumer failed to start: {e}")
        logger.warning("Running without RabbitMQ consumer — projections won't sync")


async def _handle_message(message: aio_pika.IncomingMessage):
    body = json.loads(message.body.decode())
    event_type = body.get("event_type") or message.routing_key
    payload = body.get("payload", body)
    event_id = body.get("event_id")

    logger.info(f"Received event: {event_type}")

    db: Session = SessionLocal()
    try:
        # Идемпотентность — не обрабатываем дважды
        if event_id and _already_processed(db, event_id):
            logger.info(f"Event {event_id} already processed, skipping")
            return

        if "employee.created" in event_type or "employee.updated" in event_type:
            _upsert_employee(db, payload)
        elif "employee.terminated" in event_type:
            _terminate_employee(db, payload)
        elif "department.created" in event_type or "department.updated" in event_type:
            _upsert_department(db, payload)
        elif "position.created" in event_type or "position.updated" in event_type:
            _upsert_position(db, payload)

        if event_id:
            _mark_processed(db, event_id, event_type)

        db.commit()
    finally:
        db.close()


def _already_processed(db: Session, event_id: str) -> bool:
    from sqlalchemy import text
    result = db.execute(
        text("SELECT 1 FROM processed_inbound_events WHERE event_id = :id"),
        {"id": event_id}
    ).fetchone()
    return result is not None


def _mark_processed(db: Session, event_id: str, event_type: str):
    from sqlalchemy import text
    db.execute(
        text("INSERT INTO processed_inbound_events (event_id, event_type, received_at) VALUES (:id, :type, :at)"),
        {"id": event_id, "type": event_type, "at": datetime.utcnow()}
    )


def _upsert_employee(db: Session, payload: dict):
    emp_id = UUID(payload["id"])
    existing = db.query(EmployeeView).filter(EmployeeView.id == emp_id).first()

    if existing:
        existing.full_name = payload.get("fullName", existing.full_name)
        existing.personnel_number = payload.get("personnelNumber", existing.personnel_number)
        existing.status = payload.get("status", existing.status)
        existing.synced_at = datetime.utcnow()
    else:
        employee = EmployeeView(
            id=emp_id,
            personnel_number=payload.get("personnelNumber", ""),
            full_name=payload.get("fullName", ""),
            department_id=UUID(payload["departmentId"]) if payload.get("departmentId") else None,
            position_id=UUID(payload["positionId"]) if payload.get("positionId") else None,
            status=payload.get("status", "active"),
            hire_date=payload.get("hireDate"),
            synced_at=datetime.utcnow(),
        )
        db.add(employee)
        db.flush()

        # Создаём пустой профиль
        parts = payload.get("fullName", "").split()
        profile = EmployeeProfile(
            employee_id=emp_id,
            last_name=parts[0] if len(parts) > 0 else None,
            first_name=parts[1] if len(parts) > 1 else None,
            patronymic=parts[2] if len(parts) > 2 else None,
        )
        db.add(profile)


def _terminate_employee(db: Session, payload: dict):
    emp_id = UUID(payload["id"])
    emp = db.query(EmployeeView).filter(EmployeeView.id == emp_id).first()
    if emp:
        emp.status = "terminated"
        emp.termination_date = datetime.utcnow().date()
        emp.synced_at = datetime.utcnow()

    # Блокируем все карты
    from app.models.access import AccessCard
    db.query(AccessCard).filter(
        AccessCard.employee_id == emp_id,
        AccessCard.status == "active",
    ).update({"status": "blocked", "blocked_reason": "Employee terminated"})


def _upsert_department(db: Session, payload: dict):
    dept_id = UUID(payload["id"])
    existing = db.query(DepartmentView).filter(DepartmentView.id == dept_id).first()
    if existing:
        existing.name = payload.get("name", existing.name)
        existing.code = payload.get("code", existing.code)
    else:
        db.add(DepartmentView(
            id=dept_id,
            name=payload.get("name", ""),
            code=payload.get("code", ""),
            type=payload.get("type"),
            parent_id=UUID(payload["parentId"]) if payload.get("parentId") else None,
        ))


def _upsert_position(db: Session, payload: dict):
    pos_id = UUID(payload["id"])
    existing = db.query(PositionView).filter(PositionView.id == pos_id).first()
    if existing:
        existing.title = payload.get("title", existing.title)
    else:
        db.add(PositionView(
            id=pos_id,
            title=payload.get("title", ""),
            code=payload.get("code"),
            department_id=UUID(payload["departmentId"]) if payload.get("departmentId") else None,
        ))