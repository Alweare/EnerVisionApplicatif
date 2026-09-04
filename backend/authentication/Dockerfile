# Image officielle Keycloak, avec notre realm pré-configuré importé au
# démarrage — "Realm et clients configurés" devient reproductible depuis le
# repo plutôt que dépendant d'une config faite à la main dans la console admin.
FROM quay.io/keycloak/keycloak:26.7.3

# realm-export.json est un TEMPLATE (placeholders __XXX__, aucune vraie valeur) :
# les vrais secrets clients viennent des Docker secrets, injectés par entrypoint.sh
# au démarrage — jamais gravés dans l'image ni committés dans le repo.
COPY backend/authentication/realm-export.json /opt/keycloak/data/import-template/realm-export.json
COPY --chown=1000:0 backend/authentication/entrypoint.sh /opt/keycloak/entrypoint.sh
RUN chmod +x /opt/keycloak/entrypoint.sh

# start-dev : pas de certificat/hostname à configurer pour ce ticket (Keycloak
# reste interne au réseau docker, Traefik n'est pas encore branché dessus).
# À remplacer par `start` + config hostname/proxy le jour où Keycloak doit
# être exposé publiquement.
ENTRYPOINT ["/opt/keycloak/entrypoint.sh"]
