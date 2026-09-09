FROM python:3.12.14-slim-trixie

WORKDIR /backend

COPY backend/workeringestion/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backend/workeringestion/ ./workeringestion

COPY backend/shared/ ./shared/

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import sys; from shared import heartbeat; sys.exit(0 if heartbeat.est_frais(300) else 1)"

CMD ["python", "-m", "workeringestion.main"]