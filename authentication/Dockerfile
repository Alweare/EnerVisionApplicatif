FROM quay.io/keycloak/keycloak:26.7.3

COPY authentication/realm-export.json /opt/keycloak/data/import-template/realm-export.json
COPY --chown=1000:0 authentication/entrypoint.sh /opt/keycloak/entrypoint.sh
RUN chmod +x /opt/keycloak/entrypoint.sh \
 && /opt/keycloak/bin/kc.sh build --db=postgres

# Compte non-root de l'image officielle Keycloak (UID 1000, groupe 0), déjà
# actif dans l'image de base : rendu explicite pour ne pas dépendre du défaut.
USER 1000

ENTRYPOINT ["/opt/keycloak/entrypoint.sh"]
