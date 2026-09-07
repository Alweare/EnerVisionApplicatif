#!/bin/sh
set -eu

BACKEND_SECRET="$(cat /run/secrets/keycloak_client_secret)"
FRONTEND_SECRET="$(cat /run/secrets/keycloak_frontend_client_secret)"

mkdir -p /opt/keycloak/data/import

sed \
  -e "s|__BACKEND_API_CLIENT_SECRET__|${BACKEND_SECRET}|g" \
  -e "s|__FRONTEND_CLIENT_SECRET__|${FRONTEND_SECRET}|g" \
  /opt/keycloak/data/import-template/realm-export.json \
  > /opt/keycloak/data/import/realm-export.json

export KC_DB_PASSWORD="$(cat /run/secrets/keycloak_db_password)"

exec /opt/keycloak/bin/kc.sh start --optimized --import-realm
