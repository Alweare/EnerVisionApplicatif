#!/usr/bin/env bash

set -Eeuo pipefail

# ============================================================
# LOGGING
# ============================================================

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

error() {
    printf '[%s] ERROR: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
}


# ============================================================
# VALIDATION DES VARIABLES
# ============================================================

if [[ -z "${SERVICE:-}" ]]; then
    error "SERVICE est obligatoire."
    exit 1
fi

if [[ -z "${IMAGE:-}" ]]; then
    error "IMAGE est obligatoire."
    exit 1
fi


# ============================================================
# SERVICES AUTORISÉS
# ============================================================

case "$SERVICE" in
    etl|core|prediction|workeringestion|frontend|db|mlflow)
        ;;
    *)
        error "Service non autorisé : $SERVICE"
        exit 1
        ;;
esac


# ============================================================
# DÉBUT DU DÉPLOIEMENT
# ============================================================

log "Déploiement de $SERVICE"
log "Image : $IMAGE"


# ============================================================
# PULL DE L'IMAGE
# ============================================================

log "Pull de l'image..."

docker pull "$IMAGE"


# ============================================================
# DB : MIGRATION ONE-SHOT
# ============================================================
#
# Le conteneur db n'est PAS un service permanent.
#
# Son CMD exécute :
#   pyway validate
#   pyway migrate
#   python set_app_password.py
#
# Le fichier .pyway.conf est stocké uniquement sur le serveur :
#
#   /opt/enervisionG3/secrets/.pyway.conf
#
# et monté en lecture seule dans :
#
#   /app/.pyway.conf
#
# ============================================================

if [[ "$SERVICE" == "db" ]]; then

    PYWAY_CONFIG="/opt/enervisionG3/secrets/.pyway.conf"

    # --------------------------------------------------------
    # Vérification de la configuration PyWay
    # --------------------------------------------------------

    if [[ ! -f "$PYWAY_CONFIG" ]]; then
        error "Configuration PyWay introuvable : $PYWAY_CONFIG"
        exit 1
    fi

    log "Configuration PyWay trouvée."
    log "Exécution des migrations de base de données..."

    # --------------------------------------------------------
    # Nettoyage d'une éventuelle ancienne exécution
    # --------------------------------------------------------

    docker rm -f db >/dev/null 2>&1 || true

    # --------------------------------------------------------
    # Exécution de la migration
    # --------------------------------------------------------

    if docker run \
        --name db \
        --network g3_default \
        --env-file /opt/enervisionG3/.env \
        -v /opt/enervisionG3/secrets:/run/secrets:ro \
        -v "$PYWAY_CONFIG:/app/.pyway.conf:ro" \
        "$IMAGE"
    then

        log "Migrations exécutées avec succès."

        docker rm db >/dev/null 2>&1 || true

        log "Conteneur db supprimé."

        exit 0

    else

        EXIT_CODE=$(docker inspect \
            --format '{{.State.ExitCode}}' \
            db 2>/dev/null || echo "inconnu")

        error "Les migrations ont échoué (exit code $EXIT_CODE)."

        log "Derniers logs du conteneur db :"

        docker logs --tail 100 db 2>/dev/null || true

        exit 1
    fi
fi


# ============================================================
# SERVICES PERMANENTS
# ============================================================

PREVIOUS_IMAGE=""

if docker inspect "$SERVICE" >/dev/null 2>&1; then

    PREVIOUS_IMAGE=$(docker inspect \
        --format '{{.Config.Image}}' \
        "$SERVICE")

    log "Image précédente : $PREVIOUS_IMAGE"
fi


# ============================================================
# SUPPRESSION DE L'ANCIEN CONTENEUR
# ============================================================

log "Suppression de l'ancien conteneur..."

docker rm -f "$SERVICE" 2>/dev/null || true


# ============================================================
# CONFIGURATION DES PORTS
# ============================================================

PORT_ARGS=()

if [[ "$SERVICE" == "core" ]]; then
    PORT_ARGS=(-p 8000:8000)
fi


# ============================================================
# DÉMARRAGE DU NOUVEAU CONTENEUR
# ============================================================

log "Démarrage du nouveau conteneur..."

docker run -d \
    --name "$SERVICE" \
    --restart unless-stopped \
    --network g3_default \
    --env-file /opt/enervisionG3/.env \
    -v /opt/enervisionG3/secrets:/run/secrets:ro \
    "${PORT_ARGS[@]}" \
    "$IMAGE"


# ============================================================
# VÉRIFICATION
# ============================================================

sleep 3

STATUS=$(docker inspect \
    --format '{{.State.Status}}' \
    "$SERVICE")

if [[ "$STATUS" != "running" ]]; then

    error "$SERVICE n'est pas running."

    log "Derniers logs du conteneur :"

    docker logs --tail 50 "$SERVICE" || true

    exit 1
fi


# ============================================================
# SUCCÈS
# ============================================================

log "$SERVICE déployé avec succès."