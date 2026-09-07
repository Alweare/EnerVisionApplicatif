FROM python:3.12.14-slim-trixie

WORKDIR /backend

COPY backend/core/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backend/core ./core/
COPY backend/shared/ ./shared/

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
