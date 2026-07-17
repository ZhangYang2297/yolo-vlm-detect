import json
from typing import Optional, Any
import redis
from config.settings import get_settings
from core.logger import get_logger
from core import metrics

logger = get_logger(__name__)

_redis_pool: Optional[redis.ConnectionPool] = None
_redis_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _redis_pool, _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_pool = redis.ConnectionPool(
            host=settings.redis.host,
            port=settings.redis.port,
            db=settings.redis.db,
            password=settings.redis.password,
            decode_responses=False,
            max_connections=50,
            socket_timeout=5,
            socket_connect_timeout=5,
            socket_keepalive=True,
        )
        _redis_client = redis.Redis(connection_pool=_redis_pool)
        _redis_client.ping()
        logger.info("redis_connected", host=settings.redis.host, port=settings.redis.port)
    return _redis_client


def enqueue(queue_name: str, data: dict) -> bool:
    try:
        r = get_redis()
        payload = json.dumps(data, ensure_ascii=False, default=str)
        r.rpush(queue_name, payload)
        metrics.QUEUE_PUT_TOTAL.labels(queue_name=queue_name).inc()
        current_size = r.llen(queue_name)
        metrics.QUEUE_SIZE.labels(queue_name=queue_name).set(current_size)
        return True
    except Exception as e:
        logger.error("enqueue_failed", queue=queue_name, error=str(e))
        return False


def dequeue(queue_name: str, timeout: int = 1) -> Optional[dict]:
    try:
        r = get_redis()
        result = r.blpop(queue_name, timeout=timeout)
        if result is None:
            return None
        _, payload = result
        metrics.QUEUE_GET_TOTAL.labels(queue_name=queue_name).inc()
        current_size = r.llen(queue_name)
        metrics.QUEUE_SIZE.labels(queue_name=queue_name).set(current_size)
        return json.loads(payload)
    except Exception as e:
        logger.error("dequeue_failed", queue=queue_name, error=str(e))
        return None


def set_result(key: str, data: Any, ttl: int = 3600) -> None:
    try:
        r = get_redis()
        r.setex(f"result:{key}", ttl, json.dumps(data, ensure_ascii=False, default=str))
    except Exception as e:
        logger.error("set_result_failed", key=key, error=str(e))


def get_result(key: str) -> Optional[Any]:
    try:
        r = get_redis()
        data = r.get(f"result:{key}")
        if data:
            return json.loads(data)
    except Exception as e:
        logger.error("get_result_failed", key=key, error=str(e))
    return None


def publish(channel: str, message: dict) -> None:
    try:
        r = get_redis()
        r.publish(channel, json.dumps(message, ensure_ascii=False, default=str))
    except Exception as e:
        logger.error("publish_failed", channel=channel, error=str(e))


def subscribe(channel: str):
    r = get_redis()
    pubsub = r.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(channel)
    return pubsub


def get_queue_size(queue_name: str) -> int:
    try:
        r = get_redis()
        return r.llen(queue_name)
    except Exception:
        return 0
