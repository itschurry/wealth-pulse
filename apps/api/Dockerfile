FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/apps/api

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/api ./apps/api

WORKDIR /app/apps/api

EXPOSE 8001

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8001"]
