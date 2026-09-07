FROM python:3.12.14-slim-trixie

WORKDIR /backend

COPY backend/health/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backend/health/ ./health/

EXPOSE 8000

CMD ["uvicorn", "health.main:app", "--host", "0.0.0.0", "--port", "8000"]
