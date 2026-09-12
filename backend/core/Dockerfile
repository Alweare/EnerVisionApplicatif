FROM python:3.12.14-slim-trixie

WORKDIR /backend

# Compte applicatif non-root (UID/GID fixes : permissions prévisibles sur les
# volumes montés, ex. /run/secrets). Le code copié reste propriété de root :
# le service peut le lire mais pas le modifier.
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --create-home --home-dir /home/app app

COPY backend/core/requirements.txt .

# --only-binary : wheels uniquement, aucun setup.py exécuté au build (toutes
# les dépendances, transitives comprises, publient des wheels cp312 manylinux).
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt

COPY backend/core ./core/
COPY backend/shared/ ./shared/

USER app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"

CMD ["uvicorn", "core.main:app", "--host", "0.0.0.0", "--port", "8000"]
