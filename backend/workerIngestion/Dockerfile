FROM python:3.12.14-slim-trixie

WORKDIR /backend

COPY backend/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backend/__init__.py ./backend/__init__.py
COPY backend/core/ ./backend/core/
COPY backend/workerIngestion/ ./backend/workerIngestion/

EXPOSE 8000

CMD ["uvicorn", "backend.workerIngestion.main:app", "--host", "0.0.0.0", "--port", "8000"]
