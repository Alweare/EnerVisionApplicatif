FROM python:3.12.14-slim-trixie

WORKDIR /backend

COPY backend/prediction/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backend/prediction/ ./prediction/
COPY backend/shared/ ./shared/

CMD ["python", "-m", "prediction.main"]
