FROM quay.io/keycloak/keycloak:26.7.3

COPY authentication/realm-export.json /opt/keycloak/data/import-template/realm-export.json
COPY --chown=1000:0 authentication/entrypoint.sh /opt/keycloak/entrypoint.sh
RUN chmod +x /opt/keycloak/entrypoint.sh

RUN /opt/keycloak/bin/kc.sh build --db=postgres

ENTRYPOINT ["/opt/keycloak/entrypoint.sh"]
