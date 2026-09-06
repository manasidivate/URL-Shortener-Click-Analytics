from flask_sqlalchemy import SQLAlchemy
import redis 
from rq import Queue

db = SQLAlchemy()

redis_client = redis.Redis( 
    host="localhost",       
    port=6379,              
    decode_responses=True   
)

rq_queue = Queue(
    "click_events",
    connection=redis.Redis(
        host="localhost",
        port=6379
    )
)