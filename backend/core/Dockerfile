FROM python:3.12.14-slim-trixie

WORKDIR /backend

COPY backend/core/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backend/core ./core/
COPY backend/shared/ ./shared/

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"

CMD ["uvicorn", "core.main:app", "--host", "0.0.0.0", "--port", "8000"]
