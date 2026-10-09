from app import create_app
from extensions import rq_queue
from rq import Worker

app = create_app()

with app.app_context():
    worker = Worker(
        [rq_queue],
        connection=rq_queue.connection
    )
    worker.work()
