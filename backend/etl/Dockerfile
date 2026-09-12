FROM python:3.12.14-slim-trixie

WORKDIR /backend

# Compte applicatif non-root (UID/GID fixes : permissions prévisibles sur les
# volumes montés). Le code copié reste propriété de root (lecture seule pour
# le service) ; seul /backend lui appartient, pour le fichier de heartbeat
# (HEARTBEAT_FILE=/backend/heartbeat dans docker-compose).
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --create-home --home-dir /home/app app \
 && chown app:app /backend

COPY backend/etl/requirements.txt .

# --only-binary : wheels uniquement, aucun setup.py exécuté au build (toutes
# les dépendances, transitives comprises, publient des wheels cp312 manylinux).
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt

COPY backend/etl/ ./etl/
COPY backend/shared/ ./shared/

USER app

HEALTHCHECK --interval=60s --timeout=10s --start-period=120s --retries=3 \
  CMD python -c "import sys; from shared import heartbeat; sys.exit(0 if heartbeat.est_frais(600) else 1)"

CMD ["python", "-m", "etl.main"]
