from typing import Any

import redis

from app.core.config import settings

redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

def get_redis() -> Any:
    return redis_client
