"""Celery app for background jobs (OCR processing, AI analysis, notifications, PDF, …).

Run a worker with:  celery -A app.celery_app worker --loglevel=info
With CELERY_TASK_ALWAYS_EAGER=true (the local default) tasks run inline in the caller, so no
worker is needed for `pip install + uvicorn`; docker-compose runs a real worker against Redis.
"""

from celery import Celery

from .config import settings

celery = Celery("cm", broker=settings.broker_url, backend=settings.result_backend)
celery.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_max_tasks_per_child=200,
    timezone="UTC",
    # named queues (room to grow — docs/14 §4)
    task_default_queue="default",
    task_routes={"ocr.*": {"queue": "ocr"}},
)

# register task modules
from . import tasks  # noqa: E402,F401
