FROM python:3.12.14-slim-trixie

WORKDIR /backend

# Compte applicatif non-root (UID/GID fixes : permissions prévisibles sur les
# volumes montés). Le code copié reste propriété de root : le service peut le
# lire mais pas le modifier. Les fichiers temporaires (artefacts MLflow
# téléchargés, etc.) vont dans /tmp ou le HOME du compte.
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --create-home --home-dir /home/app app

COPY backend/prediction/requirements.txt .

# --only-binary : wheels uniquement, aucun setup.py exécuté au build (toutes
# les dépendances, transitives comprises, publient des wheels cp312 manylinux).
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt

COPY backend/prediction/ ./prediction/
COPY backend/shared/ ./shared/

USER app

EXPOSE 8000

# Le service tourne derrière le reverse proxy : il doit écouter sur toutes les
# interfaces du conteneur. L'hôte est fourni par l'environnement (jamais codé
# en dur dans le code Python -- voir prediction/main.py::_run_serve).
ENV PREDICTION_HOST=0.0.0.0

CMD ["python", "-m", "prediction.main", "serve"]
