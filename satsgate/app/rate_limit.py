import time
import redis.asyncio as redis
import os

RL_ENABLED = os.environ.get("SATSGATE_RL_ENABLED", "1") != "0"

if RL_ENABLED:
    REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
    REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
    REDIS_URL = os.environ.get("REDIS_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/0")
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
else:
    class MockRedis:
        def __init__(self): self.data = {}
        def pipeline(self): return self
        def incr(self, key): pass
        def expire(self, key, time): pass
        def incrby(self, key, amount): pass
        async def execute(self): return [0, 0, 0]
        async def get(self, key): return self.data.get(key)
        async def setex(self, key, time, val): self.data[key] = val
    redis_client = MockRedis()

async def check_rate_limit(api_key_hash: str | None, ip: str) -> tuple[bool, int]:
    """Returns (allowed, retry_after_seconds)."""
    now = int(time.time())
    
    if api_key_hash:
        key_sec = f"rl:sec:{api_key_hash}:{now}"
        key_min = f"rl:min:{api_key_hash}:{now // 60}"
        limit_sec = int(os.environ.get("RATE_LIMIT_PER_SEC", "10"))
        limit_min = int(os.environ.get("RATE_LIMIT_PER_MIN", "100"))
    else:
        key_sec = f"rl:sec:ip:{ip}:{now}"
        key_min = f"rl:min:ip:{ip}:{now // 60}"
        limit_sec = int(os.environ.get("RATE_LIMIT_PER_SEC", "5"))
        limit_min = int(os.environ.get("RATE_LIMIT_PER_MIN", "30"))

    pipe = redis_client.pipeline()
    pipe.incr(key_sec)
    pipe.expire(key_sec, 2)
    pipe.incr(key_min)
    pipe.expire(key_min, 62)
    
    results = await pipe.execute()
    count_sec = results[0]
    count_min = results[2]

    if count_sec > limit_sec:
        return False, 1
    if count_min > limit_min:
        return False, 60 - (now % 60)
        
    return True, 0


async def check_daily_limit(api_key_hash: str, cost: int) -> bool:
    now = int(time.time())
    today = now // 86400
    key = f"daily_spend:{api_key_hash}:{today}"
    limit = int(os.environ.get("DAILY_SPEND_LIMIT", "2000"))
    
    current = await redis_client.get(key)
    if current and int(current) + cost > limit:
        return False
    return True

async def increment_daily_spend(api_key_hash: str, cost: int) -> None:
    now = int(time.time())
    today = now // 86400
    key = f"daily_spend:{api_key_hash}:{today}"
    pipe = redis_client.pipeline()
    pipe.incrby(key, cost)
    pipe.expire(key, 86400 * 2)
    await pipe.execute()

async def check_idempotency(idempotency_key: str) -> str | None:
    if not idempotency_key:
        return None
    key = f"idem:{idempotency_key}"
    return await redis_client.get(key)

async def set_idempotency(idempotency_key: str, response: str) -> None:
    if not idempotency_key:
        return
    key = f"idem:{idempotency_key}"
    await redis_client.setex(key, 86400, response)
