FROM python:3.12.14-slim-trixie

WORKDIR /backend

COPY backend/etl/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backend/etl/ ./etl/
COPY backend/shared/ ./shared/

HEALTHCHECK --interval=60s --timeout=10s --start-period=120s --retries=3 \
  CMD python -c "import sys; from shared import heartbeat; sys.exit(0 if heartbeat.est_frais(600) else 1)"

CMD ["python", "-m", "etl.main"]
