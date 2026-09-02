from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from backend.core.schemas import ErrorDetail
from backend.workerIngestion import service
from backend.workerIngestion.schemas import (
    Alert,
    EnergyReading,
    SimulateSpikeResult,
    Site,
    SiteSensorsStatus,
    StatsSummary,
)

sites_router = APIRouter(prefix="/api/v1/sites", tags=["Worker Ingestion"])
readings_router = APIRouter(prefix="/api/v1/readings", tags=["Worker Ingestion"])
sensors_router = APIRouter(prefix="/api/v1/sensors", tags=["Worker Ingestion"])
alerts_router = APIRouter(prefix="/api/v1/alerts", tags=["Worker Ingestion"])
stats_router = APIRouter(prefix="/api/v1/stats", tags=["Worker Ingestion"])
simulate_router = APIRouter(prefix="/api/v1/simulate", tags=["Worker Ingestion"])


@sites_router.get(
    "",
    response_model=list[Site],
    summary="Liste tous les sites",
    description="Retourne tous les sites disponibles et leurs caractéristiques statiques.",
)
async def get_sites() -> list[Site]:
    return await service.list_sites()


@sites_router.get(
    "/{site_id}",
    response_model=Site,
    summary="Détail d'un site",
    description="Retourne les caractéristiques statiques d'un site donné.",
    responses={404: {"model": ErrorDetail, "description": "Site inexistant"}},
)
async def get_site_detail(site_id: str) -> Site:
    try:
        return await service.get_site(site_id)
    except service.SiteNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@sites_router.get(
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
    try:
        return await service.get_current_reading(site_id)
    except service.SiteNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@readings_router.get(
    "",
    response_model=list[EnergyReading],
    summary="Historique de lectures, filtrable par site",
    description=(
        "Retourne un historique de lectures sur une période donnée, trié par "
        "timestamp croissant. `site_id` est optionnel (tous les sites si "
        "omis). Par défaut, la période couvre les dernières 24h et la "
        "réponse est limitée à 100 lectures. Relaie tel quel le comportement "
        "de la Mock API (pas de validation `start_time`/`end_time` de notre "
        "côté, pour rester un miroir fidèle)."
    ),
    responses={404: {"model": ErrorDetail, "description": "Site inexistant (si site_id fourni)"}},
)
async def get_readings(
    site_id: str | None = Query(default=None, description="Filtrer par site (ex : SITE001)"),
    start_time: datetime | None = Query(
        default=None, description="Début de la période (ISO 8601), défaut : il y a 24h"
    ),
    end_time: datetime | None = Query(
        default=None, description="Fin de la période (ISO 8601), défaut : maintenant"
    ),
    limit: int = Query(default=100, ge=1, le=1000, description="Nombre de résultats (1-1000)"),
) -> list[EnergyReading]:
    try:
        return await service.get_readings(site_id, start_time, end_time, limit)
    except service.SiteNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


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
    return await service.get_sensors_status()


@alerts_router.get(
    "",
    response_model=list[Alert],
    summary="Liste les alertes de consommation actives",
    description=(
        "Retourne les alertes actives, avec filtrage optionnel et combinable "
        "par `site_id` et `severity`. Une `severity` non reconnue renvoie une "
        "liste vide (comportement de la Mock API, pas de 422 de notre côté)."
    ),
)
async def get_alerts_route(
    site_id: str | None = Query(default=None, description="Filtrer par site (ex : SITE001)"),
    severity: str | None = Query(
        default=None, description="Filtrer par sévérité (low/medium/high/critical)"
    ),
) -> list[Alert]:
    return await service.get_alerts(site_id=site_id, severity=severity)


@stats_router.get(
    "/summary",
    response_model=StatsSummary,
    summary="Résumé agrégé du parc de sites",
    description=(
        "Retourne les agrégats du parc (consommation totale, capacité totale, "
        "taux de charge moyen), calculés côté Mock API. Les sites dont "
        "`current_consumption_kw` est `null` sont déjà exclus de "
        "`total_consumption_kw`/`average_load_percent` par la Mock API elle-même. "
        "`has_incomplete_data` est ajouté par notre service : `true` dès qu'un "
        "site est en `data_quality` `critical`."
    ),
)
async def get_stats_summary_route() -> StatsSummary:
    return await service.get_stats_summary()


@simulate_router.post(
    "/spike/{site_id}",
    response_model=SimulateSpikeResult,
    summary="Déclenche un pic de consommation fictif",
    description=(
        "Déclenche un événement fictif de pic de consommation sur un site, "
        "pour tester les alertes et pipelines de détection d'anomalies. "
        "⚠️ Mutation sur la Mock API partagée par la cohorte."
    ),
    responses={404: {"model": ErrorDetail, "description": "Site inexistant"}},
)
async def simulate_spike(
    site_id: str,
    duration_minutes: int = Query(default=30, ge=1, le=240, description="Durée du pic (1-240 min)"),
) -> SimulateSpikeResult:
    try:
        return await service.simulate_spike(site_id, duration_minutes)
    except service.SiteNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
