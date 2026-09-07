#!/usr/bin/env bash

set -Eeuo pipefail

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

error() {
    printf '[%s] ERROR: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
}

if [[ -z "${SERVICE:-}" ]]; then
    error "SERVICE est obligatoire."
    exit 1
fi

if [[ -z "${IMAGE:-}" ]]; then
    error "IMAGE est obligatoire."
    exit 1
fi

case "$SERVICE" in
    etl|consumption|prediction|recommandation|health|authentication|core|frontend)
        ;;
    *)
        error "Service non autorisé : $SERVICE"
        exit 1
        ;;
esac

log "Déploiement de $SERVICE"
log "Image : $IMAGE"

log "Pull de l'image..."
docker pull "$IMAGE"

PREVIOUS_IMAGE=""

if docker inspect "$SERVICE" >/dev/null 2>&1; then
    PREVIOUS_IMAGE=$(docker inspect \
        --format '{{.Config.Image}}' \
        "$SERVICE")

    log "Image précédente : $PREVIOUS_IMAGE"
fi

log "Suppression de l'ancien conteneur..."
docker rm -f "$SERVICE" 2>/dev/null || true

log "Démarrage du nouveau conteneur..."

case "$SERVICE" in

    etl)
        docker run -d \
            --name etl \
            --restart unless-stopped \
            --network g3_default \
            "$IMAGE"
        ;;

    health)
        docker run -d \
            --name health \
            --restart unless-stopped \
            --network g3_default \
            -p 8000:8000 \
            "$IMAGE"
        ;;

    *)
        docker run -d \
            --name "$SERVICE" \
            --restart unless-stopped \
            --network g3_default \
            "$IMAGE"
        ;;
esac

sleep 3

STATUS=$(docker inspect \
    --format '{{.State.Status}}' \
    "$SERVICE")

if [[ "$STATUS" != "running" ]]; then
    error "$SERVICE n'est pas running."

    docker logs --tail 50 "$SERVICE" || true

    exit 1
fi

log "$SERVICE déployé avec succès."