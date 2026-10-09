from flask_sqlalchemy import SQLAlchemy
import os

import redis
from rq import Queue

db = SQLAlchemy()


def create_redis_clients(redis_url):
    """Create separate cache and RQ clients from one Redis connection URL."""
    cache_client = redis.Redis.from_url(
        redis_url,
        decode_responses=True,
    )
    queue_connection = redis.Redis.from_url(redis_url)
    return cache_client, queue_connection


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client, rq_connection = create_redis_clients(REDIS_URL)

rq_queue = Queue(
    "click_events",
    connection=rq_connection,
)
