import os
import json
import hashlib
from datetime import datetime
from typing import Optional

from redis.asyncio import Redis
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://121.40.124.210:6379/0")

_redis_client: Optional[Redis] = None


async def init_redis() -> Redis:
    """初始化Redis连接"""
    global _redis_client
    _redis_client = Redis.from_url(
        REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    await _redis_client.ping()
    return _redis_client


async def close_redis():
    """关闭Redis连接"""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


def get_redis() -> Optional[Redis]:
    """获取Redis客户端实例，未初始化时返回None"""
    return _redis_client


def make_cache_key(strategy_type: str, identifier: str, params: dict = None) -> str:
    """
    生成缓存key

    格式: strategy:{type}:{identifier}:{params_hash}:{date}
    包含日期实现自然每日失效
    """
    today = datetime.now().strftime("%Y-%m-%d")
    if params:
        params_str = json.dumps(params, sort_keys=True)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
    else:
        params_hash = "default"
    return f"strategy:{strategy_type}:{identifier}:{params_hash}:{today}"


def make_running_key(cache_key: str) -> str:
    """生成执行中标记key"""
    return f"{cache_key}:running"


def get_ttl_seconds() -> int:
    """计算到当天23:59:59的剩余秒数，最少1小时"""
    now = datetime.now()
    end_of_day = now.replace(hour=23, minute=59, second=59)
    remaining = int((end_of_day - now).total_seconds())
    return max(remaining, 3600)