#!/bin/sh
# Injecte les secrets Docker (jamais commités) dans le template de realm au
# démarrage, pour que realm-export.json committé dans le repo ne contienne
# aucune vraie valeur — seulement des placeholders __XXX__.
set -eu

BACKEND_SECRET="$(cat /run/secrets/keycloak_client_secret)"
FRONTEND_SECRET="$(cat /run/secrets/keycloak_frontend_client_secret)"

mkdir -p /opt/keycloak/data/import

sed \
  -e "s|__BACKEND_API_CLIENT_SECRET__|${BACKEND_SECRET}|g" \
  -e "s|__FRONTEND_CLIENT_SECRET__|${FRONTEND_SECRET}|g" \
  /opt/keycloak/data/import-template/realm-export.json \
  > /opt/keycloak/data/import/realm-export.json

# Mot de passe de la DB Keycloak : même mécanique que les secrets clients
# ci-dessus (fichier Docker secret, jamais en clair dans une image/le repo).
export KC_DB_PASSWORD="$(cat /run/secrets/keycloak_db_password)"

exec /opt/keycloak/bin/kc.sh start-dev --import-realm
