FROM python:3.12.14-slim-trixie

WORKDIR /backend

COPY backend/prediction/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backend/prediction/ ./prediction/
COPY backend/shared/ ./shared/

EXPOSE 8000

# Le service tourne derrière le reverse proxy : il doit écouter sur toutes les
# interfaces du conteneur. L'hôte est fourni par l'environnement (jamais codé
# en dur dans le code Python -- voir prediction/main.py::_run_serve).
ENV PREDICTION_HOST=0.0.0.0

CMD ["python", "-m", "prediction.main", "serve"]
