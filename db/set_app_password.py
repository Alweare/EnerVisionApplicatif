import os

import psycopg2
from psycopg2 import sql

conn = psycopg2.connect(
    host=os.environ["PYWAY_DATABASE_HOST"],
    port=os.environ.get("PYWAY_DATABASE_PORT", "5432"),
    dbname=os.environ["PYWAY_DATABASE_NAME"],
    user=os.environ["PYWAY_DATABASE_USERNAME"],
    password=os.environ["PYWAY_DATABASE_PASSWORD"],
)
conn.autocommit = True

app_user = os.environ["APP_DB_USER"]
app_password = os.environ["APP_DB_PASSWORD"]

with conn.cursor() as cursor:
    cursor.execute(
        sql.SQL("ALTER USER {} WITH PASSWORD %s").format(sql.Identifier(app_user)),
        (app_password,),
    )

conn.close()
print(f"Mot de passe de l'utilisateur '{app_user}' mis à jour.")
