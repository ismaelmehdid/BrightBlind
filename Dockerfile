FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

COPY recall/ recall/

# Railway sets PORT; attach a volume at /data so the SQLite memory survives redeploys.
CMD ["python", "-m", "recall.cloud"]
