import os

# core.database lit ces variables au moment de l'import (os.environ[...]).
# On pose des valeurs factices pour que l'import des contrôleurs / de l'app
# fonctionne en test sans base réelle — les connexions sont neutralisées
# via l'override de get_db dans test_routes.py.
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("POSTGRES_APP_USER", "test")
os.environ.setdefault("POSTGRES_APP_PWD", "test")
