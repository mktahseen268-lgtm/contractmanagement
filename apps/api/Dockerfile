FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

EXPOSE 8000
# default = the API; the worker service overrides this with `celery -A app.celery_app worker ...`
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
