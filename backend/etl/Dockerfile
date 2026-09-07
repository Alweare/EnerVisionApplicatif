FROM python:3.12.14-slim-trixie

WORKDIR /backend

COPY backend/etl/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backend/etl/ ./etl/
COPY backend/shared/ ./shared/

CMD ["python", "-m", "etl.main"]
