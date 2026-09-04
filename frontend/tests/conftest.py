import os

# services/*.py lisent BACKEND_URL au moment de l'import (os.environ[...]).
# On pose une valeur factice pour que la collecte des tests fonctionne sans
# backend réel — aucune requête HTTP n'est faite tant que les services
# renvoient des mocks.
os.environ.setdefault("BACKEND_URL", "http://backend:8000")
