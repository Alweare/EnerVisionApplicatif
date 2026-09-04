FROM python:3.12.14-slim-bookworm

WORKDIR /app

COPY backend/health/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backend/health/ .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]