import os

# On pose des valeurs factices pour que l'import des contrôleurs / de l'app
# fonctionne en tests sans base réelle — les connexions sont neutralisées
# via l'override de get_db dans test_routes.py.
os.environ.setdefault("POSTGRES_DB", "tests")
os.environ.setdefault("POSTGRES_APP_USER", "tests")
os.environ.setdefault("POSTGRES_APP_PWD", "tests")
