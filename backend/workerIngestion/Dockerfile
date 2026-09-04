FROM python:3.12.14-slim-trixie

WORKDIR /backend

COPY backend/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backend/core/ ./core/
COPY backend/workerIngestion/ ./workerIngestion/

CMD ["python", "-m", "workerIngestion.main"]
