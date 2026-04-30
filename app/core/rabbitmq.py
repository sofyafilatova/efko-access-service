import aio_pika
import json
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

_connection = None
_channel = None
EXCHANGE_NAME = "efko.access.events"


async def get_channel():
    global _connection, _channel
    if _channel is None or _channel.is_closed:
        _connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        _channel = await _connection.channel()
        exchange = await _channel.declare_exchange(
            EXCHANGE_NAME,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
    return _channel, exchange


async def publish_event(event_type: str, payload: dict, correlation_id: str | None = None):
    """
    Публикует событие в RabbitMQ.
    routing_key = event_type (напр. access.attendance.checked_in)
    """
    try:
        channel, exchange = await get_channel()
        body = json.dumps({
            "event_type": event_type,
            "payload": payload,
            "correlation_id": correlation_id,
        }, default=str).encode()

        await exchange.publish(
            aio_pika.Message(
                body=body,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=event_type,
        )
        logger.info(f"Event published: {event_type}")
    except Exception as e:
        logger.error(f"Failed to publish event {event_type}: {e}")
        # Не бросаем исключение — бизнес-логика не должна падать из-за RabbitMQ


async def close():
    global _connection
    if _connection:
        await _connection.close()