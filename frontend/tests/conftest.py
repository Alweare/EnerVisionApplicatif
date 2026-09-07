import os

# services/*.py lisent BACKEND_URL au moment de l'import (os.environ[...]).
# On pose une valeur factice pour que la collecte des tests fonctionne sans
# dépendre de l'environnement d'exécution (docker-compose définit la vraie
# valeur en dev/prod) ; requests.get est mocké dans chaque test, aucune
# requête HTTP réelle n'est faite vers cette URL.
os.environ.setdefault("BACKEND_URL", "http://backend:8000")
