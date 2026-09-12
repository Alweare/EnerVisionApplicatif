FROM python:3.12.14-slim-trixie
WORKDIR /frontend

# Compte applicatif non-root (UID/GID fixes : permissions prévisibles sur le
# secrets.toml monté). Le code copié reste propriété de root : le service peut
# le lire mais pas le modifier.
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --create-home --home-dir /home/app app

COPY requirements.txt .
# --only-binary : wheels uniquement, aucun setup.py exécuté au build.
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt

# Copie ciblée du code exécuté par Streamlit (plutôt que `COPY . .`) : ni
# tests, ni .env, ni .streamlit/secrets.toml ne peuvent finir dans l'image.
# Les secrets Streamlit sont montés au runtime (voir docker-compose).
COPY app.py branding.py formatting.py ./
COPY assets/ ./assets/
COPY authentification/ ./authentification/
COPY components/ ./components/
COPY pages/ ./pages/
COPY services/ ./services/

USER app

EXPOSE 8501
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health').read()"

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
