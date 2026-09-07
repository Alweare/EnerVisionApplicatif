import os

# prediction.repository.measurement_repository importe shared.database, qui lit
# POSTGRES_* au moment de l'import (os.environ[...]). On pose des valeurs
# factices pour que la collecte des tests fonctionne sans base réelle -- les
# tests ne touchent jamais la vraie connexion : pd.read_sql est monkeypatché.
os.environ.setdefault("POSTGRES_DB", "tests")
os.environ.setdefault("POSTGRES_APP_USER", "tests")
os.environ.setdefault("POSTGRES_APP_PWD", "tests")
