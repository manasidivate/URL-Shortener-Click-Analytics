from app import create_app
from extensions import rq_queue
from rq import SimpleWorker

app = create_app()

with app.app_context():
    worker = SimpleWorker(
        [rq_queue],
        connection=rq_queue.connection
    )
    worker.work()

    