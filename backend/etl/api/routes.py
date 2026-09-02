from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from backend.core.schemas import ErrorDetail
from backend.etl.repository import (
    get_alerts,
    get_current_reading,
    get_history,
    get_sensors_status,
)
from backend.etl.schemas import Alert, AlertSeverity, EnergyReading, SiteSensorsStatus

router = APIRouter(prefix="/api/v1/sites", tags=["ETL"])
sensors_router = APIRouter(prefix="/api/v1/sensors", tags=["ETL"])
alerts_router = APIRouter(prefix="/api/v1/alerts", tags=["ETL"])


@router.get(
    "/{site_id}/current",
    response_model=EnergyReading,
    summary="Dernière lecture connue d'un site",
    description=(
        "Retourne la dernière mesure connue d'un site (consommation, tension, "
        "température...). Les champs de mesure peuvent être `null` en cas de "
        "panne capteur ou de perte réseau : `data_quality` et `null_reasons` "
        "indiquent alors la cause, sans que la lecture soit filtrée."
    ),
    responses={404: {"model": ErrorDetail, "description": "Site inexistant"}},
)
async def get_site_current_reading(site_id: str) -> EnergyReading:
    reading = get_current_reading(site_id)
    if reading is None:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' introuvable")
    return reading


@router.get(
    "/{site_id}/history",
    response_model=list[EnergyReading],
    summary="Historique paginé des lectures d'un site",
    description=(
        "Retourne l'historique des lectures d'un site sur une période donnée, "
        "triées par timestamp croissant. Par défaut, la période couvre les "
        "dernières 24h et la réponse est limitée à 100 lectures."
    ),
    responses={
        404: {"model": ErrorDetail, "description": "Site inexistant"},
        422: {
            "model": ErrorDetail,
            "description": (
                "Paramètre invalide : date au format non ISO 8601, `limit` "
                "hors de la plage 1-1000, ou `start_time` postérieur à `end_time`"
            ),
        },
    },
)
async def get_site_history(
    site_id: str,
    start_time: datetime | None = Query(
        default=None, description="Début de la période (ISO 8601), défaut : il y a 24h"
    ),
    end_time: datetime | None = Query(
        default=None, description="Fin de la période (ISO 8601), défaut : maintenant"
    ),
    limit: int = Query(default=100, ge=1, le=1000, description="Nombre de résultats (1-1000)"),
) -> list[EnergyReading]:
    now = datetime.now()
    start = (start_time or now - timedelta(hours=24)).replace(tzinfo=None)
    end = (end_time or now).replace(tzinfo=None)

    if start > end:
        raise HTTPException(
            status_code=422, detail="start_time doit être antérieur à end_time"
        )

    readings = get_history(site_id, start, end, limit)
    if readings is None:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' introuvable")
    return readings


@sensors_router.get(
    "/status",
    response_model=dict[str, SiteSensorsStatus],
    summary="État de santé des capteurs par site",
    description=(
        "Retourne, pour chaque site connu, l'état de chaque capteur "
        "(consumption/electrical/temperature/humidity/network, ok ou failing) "
        "ainsi qu'un statut global `overall` : `ok` (tous capteurs opérationnels), "
        "`degraded` (au moins un capteur en panne, données partielles) ou "
        "`critical` (perte réseau, aucune donnée disponible)."
    ),
)
async def get_sensors_status_route() -> dict[str, SiteSensorsStatus]:
    return get_sensors_status()


@alerts_router.get(
    "",
    response_model=list[Alert],
    summary="Liste les alertes de consommation actives",
    description=(
        "Retourne les alertes actives, avec filtrage optionnel et combinable "
        "par `site_id` et `severity`. Renvoie une liste vide si aucune alerte "
        "ne correspond aux filtres."
    ),
)
async def get_alerts_route(
    site_id: str | None = Query(default=None, description="Filtrer par site (ex : SITE001)"),
    severity: AlertSeverity | None = Query(default=None, description="Filtrer par sévérité"),
) -> list[Alert]:
    return get_alerts(site_id=site_id, severity=severity)
