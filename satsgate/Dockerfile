FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

COPY app ./app

EXPOSE 8000

# Use Gunicorn with Uvicorn workers for production
CMD ["gunicorn", "app.main:app", "--workers", "2", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
