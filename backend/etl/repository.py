from datetime import datetime, timedelta

from backend.etl.schemas import (
    Alert,
    EnergyReading,
    SensorsBlock,
    SensorState,
    SiteSensorsStatus,
    SiteStat,
    StatsSummary,
)
from backend.sites.repository import list_sites

# Mock en mémoire en attendant le branchement sur la Mock API / la base de
# données via l'ETL. Une seule lecture "courante" par site, choisie pour
# illustrer les 3 niveaux de data_quality documentés (good/partial/critical) :
# - SITE001 : tous capteurs OK (exemple repris tel quel de la doc Mock API)
# - SITE002 : panne du capteur de température (valeurs plausibles, non documentées)
# - SITE003 : perte réseau totale, cohérent avec le data_quality "critical"
#   observé pour ce site dans l'exemple /api/v1/stats/summary de la doc
_CURRENT_READINGS: dict[str, EnergyReading] = {
    "SITE001": EnergyReading(
        timestamp=datetime.fromisoformat("2024-06-15T14:32:00.123456"),
        site_id="SITE001",
        site_type="office",
        consumption_kw=87.34,
        consumption_kwh=87.34,
        voltage_v=401.2,
        current_a=132.5,
        power_factor=0.923,
        temperature_celsius=22.1,
        humidity_percent=58.4,
        null_reasons=[],
        data_quality="good",
    ),
    "SITE002": EnergyReading(
        timestamp=datetime.fromisoformat("2024-06-15T14:32:05.987654"),
        site_id="SITE002",
        site_type="factory",
        consumption_kw=542.10,
        consumption_kwh=542.10,
        voltage_v=398.5,
        current_a=826.4,
        power_factor=0.921,
        temperature_celsius=None,
        humidity_percent=61.8,
        null_reasons=["temperature_sensor_failure"],
        data_quality="partial",
    ),
    "SITE003": EnergyReading(
        timestamp=datetime.fromisoformat("2024-06-15T14:32:10.111111"),
        site_id="SITE003",
        site_type="datacenter",
        consumption_kw=None,
        consumption_kwh=None,
        voltage_v=None,
        current_a=None,
        power_factor=None,
        temperature_celsius=None,
        humidity_percent=None,
        null_reasons=["network_loss"],
        data_quality="critical",
    ),
}


def get_current_reading(site_id: str) -> EnergyReading | None:
    return _CURRENT_READINGS.get(site_id)


# Historique : générées à la volée (une lecture par heure pleine dans la
# fenêtre demandée), qualité "good" fixe. Base de consommation par site pour
# donner un profil plausible ; les autres capteurs restent constants, ce mock
# sert à exercer la pagination/le tri, pas la variabilité de data_quality
# (déjà couverte par get_current_reading).
_HISTORY_BASE_CONSUMPTION_KW: dict[str, float] = {
    "SITE001": 85.0,
    "SITE002": 540.0,
    "SITE003": 300.0,
}


def _generate_hourly_readings(
    site_id: str, start: datetime, end: datetime
) -> list[EnergyReading]:
    site_type = _CURRENT_READINGS[site_id].site_type
    base_kw = _HISTORY_BASE_CONSUMPTION_KW[site_id]

    timestamp = start.replace(minute=0, second=0, microsecond=0)
    if timestamp < start:
        timestamp += timedelta(hours=1)

    readings = []
    hour_index = 0
    while timestamp <= end:
        consumption = round(base_kw + (hour_index % 6) * 1.5, 2)
        readings.append(
            EnergyReading(
                timestamp=timestamp,
                site_id=site_id,
                site_type=site_type,
                consumption_kw=consumption,
                consumption_kwh=consumption,
                voltage_v=400.0,
                current_a=round(consumption * 1.44, 1),
                power_factor=0.92,
                temperature_celsius=20.0,
                humidity_percent=55.0,
                null_reasons=[],
                data_quality="good",
            )
        )
        timestamp += timedelta(hours=1)
        hour_index += 1
    return readings


def get_history(
    site_id: str, start: datetime, end: datetime, limit: int
) -> list[EnergyReading] | None:
    if site_id not in _CURRENT_READINGS:
        return None

    readings = _generate_hourly_readings(site_id, start, end)
    readings.sort(key=lambda reading: reading.timestamp)
    return readings[-limit:]


# État des capteurs : cohérent avec _CURRENT_READINGS ci-dessus (site_name
# dupliqué depuis backend.sites.repository à dessein, pour ne pas coupler les
# deux modules tant qu'ils restent des mocks indépendants) :
# - SITE001 : tous capteurs ok -> overall "ok"
# - SITE002 : capteur température en panne (données partielles) -> "degraded"
# - SITE003 : capteur réseau en panne (aucune donnée) -> "critical"
_SENSORS_STATUS: dict[str, SiteSensorsStatus] = {
    "SITE001": SiteSensorsStatus(
        site_name="Bureau Paris La Défense",
        sensors=SensorsBlock(
            consumption=SensorState(status="ok", failing_until=None),
            electrical=SensorState(status="ok", failing_until=None),
            temperature=SensorState(status="ok", failing_until=None),
            humidity=SensorState(status="ok", failing_until=None),
            network=SensorState(status="ok", failing_until=None),
        ),
        overall="ok",
    ),
    "SITE002": SiteSensorsStatus(
        site_name="Usine Lyon Vénissieux",
        sensors=SensorsBlock(
            consumption=SensorState(status="ok", failing_until=None),
            electrical=SensorState(status="ok", failing_until=None),
            temperature=SensorState(
                status="failing",
                failing_until=datetime.fromisoformat("2024-06-15T14:33:05"),
            ),
            humidity=SensorState(status="ok", failing_until=None),
            network=SensorState(status="ok", failing_until=None),
        ),
        overall="degraded",
    ),
    "SITE003": SiteSensorsStatus(
        site_name="Data Center Marseille",
        sensors=SensorsBlock(
            consumption=SensorState(status="ok", failing_until=None),
            electrical=SensorState(status="ok", failing_until=None),
            temperature=SensorState(status="ok", failing_until=None),
            humidity=SensorState(status="ok", failing_until=None),
            network=SensorState(
                status="failing",
                failing_until=datetime.fromisoformat("2024-06-15T14:40:00"),
            ),
        ),
        overall="critical",
    ),
}


def get_sensors_status() -> dict[str, SiteSensorsStatus]:
    return _SENSORS_STATUS


# Alertes : reprend l'exemple de la doc Mock API (ALR-SITE002-1718458320) et
# ajoute 3 alertes plausibles sur d'autres sites/sévérités/types pour pouvoir
# exercer le filtrage combiné site_id + severity.
_ALERTS: list[Alert] = [
    Alert(
        alert_id="ALR-SITE001-1718458200",
        timestamp=datetime.fromisoformat("2024-06-15T14:10:00"),
        site_id="SITE001",
        severity="low",
        type="threshold",
        message="Consommation légèrement au-dessus du seuil sur Bureau Paris La Défense",
        value=95.0,
        threshold=90.0,
    ),
    Alert(
        alert_id="ALR-SITE002-1718458100",
        timestamp=datetime.fromisoformat("2024-06-15T14:08:00"),
        site_id="SITE002",
        severity="medium",
        type="spike",
        message="Pic de consommation détecté sur Usine Lyon Vénissieux",
        value=650.0,
        threshold=600.0,
    ),
    Alert(
        alert_id="ALR-SITE002-1718458320",
        timestamp=datetime.fromisoformat("2024-06-15T14:12:00"),
        site_id="SITE002",
        severity="critical",
        type="outage",
        message="Risque de surcharge sur Usine Lyon Vénissieux",
        value=812.5,
        threshold=720.0,
    ),
    Alert(
        alert_id="ALR-SITE003-1718458260",
        timestamp=datetime.fromisoformat("2024-06-15T14:11:00"),
        site_id="SITE003",
        severity="high",
        type="sensor",
        message="Panne du capteur réseau sur Data Center Marseille",
        value=0.0,
        threshold=1.0,
    ),
]


def get_alerts(site_id: str | None = None, severity: str | None = None) -> list[Alert]:
    return [
        alert
        for alert in _ALERTS
        if (site_id is None or alert.site_id == site_id)
        and (severity is None or alert.severity == severity)
    ]


# Résumé du parc : seul endroit du module à dépendre de backend.sites, car il
# doit croiser les métadonnées statiques des sites (nom, capacité) avec leurs
# lectures courantes — contrairement à get_current_reading/get_sensors_status
# qui restent volontairement autonomes.
def get_stats_summary() -> StatsSummary:
    site_stats: list[SiteStat] = []
    total_consumption_kw = 0.0
    total_capacity_kw = 0
    has_incomplete_data = False

    for site in list_sites():
        reading = get_current_reading(site.site_id)
        consumption_kw = reading.consumption_kw if reading else None
        data_quality = reading.data_quality if reading else "critical"

        load_percent = (
            round(consumption_kw / site.capacity_kw * 100, 1)
            if consumption_kw is not None
            else None
        )

        if consumption_kw is not None:
            total_consumption_kw += consumption_kw
        total_capacity_kw += site.capacity_kw
        if data_quality == "critical":
            has_incomplete_data = True

        site_stats.append(
            SiteStat(
                site_id=site.site_id,
                site_name=site.site_name,
                current_consumption_kw=consumption_kw,
                capacity_kw=site.capacity_kw,
                load_percent=load_percent,
                data_quality=data_quality,
            )
        )

    average_load_percent = (
        round(total_consumption_kw / total_capacity_kw * 100, 1)
        if total_capacity_kw
        else 0.0
    )

    return StatsSummary(
        timestamp=datetime.now(),
        total_sites=len(site_stats),
        total_consumption_kw=round(total_consumption_kw, 2),
        total_capacity_kw=total_capacity_kw,
        average_load_percent=average_load_percent,
        has_incomplete_data=has_incomplete_data,
        sites=site_stats,
    )


# --- Pour plus tard : proxy vers la Mock API distante ---
# import httpx
# from backend.core.config import settings
#
# async def get_current_reading(site_id: str) -> EnergyReading | None:
#     async with httpx.AsyncClient(base_url=settings.mock_api_url) as client:
#         response = await client.get(f"/api/v1/sites/{site_id}/current")
#         if response.status_code == 404:
#             return None
#         response.raise_for_status()
#         return EnergyReading(**response.json())
#
# async def get_history(
#     site_id: str, start: datetime, end: datetime, limit: int
# ) -> list[EnergyReading] | None:
#     async with httpx.AsyncClient(base_url=settings.mock_api_url) as client:
#         response = await client.get(
#             f"/api/v1/sites/{site_id}/history",
#             params={"start_time": start.isoformat(), "end_time": end.isoformat(), "limit": limit},
#         )
#         if response.status_code == 404:
#             return None
#         response.raise_for_status()
#         return [EnergyReading(**item) for item in response.json()]
#
# async def get_sensors_status() -> dict[str, SiteSensorsStatus]:
#     async with httpx.AsyncClient(base_url=settings.mock_api_url) as client:
#         response = await client.get("/api/v1/sensors/status")
#         response.raise_for_status()
#         return {
#             site_id: SiteSensorsStatus(**status)
#             for site_id, status in response.json().items()
#         }
#
# async def get_alerts(site_id: str | None = None, severity: str | None = None) -> list[Alert]:
#     async with httpx.AsyncClient(base_url=settings.mock_api_url) as client:
#         params = {k: v for k, v in {"site_id": site_id, "severity": severity}.items() if v}
#         response = await client.get("/api/v1/alerts", params=params)
#         response.raise_for_status()
#         return [Alert(**item) for item in response.json()]
#
# async def get_stats_summary() -> StatsSummary:
#     async with httpx.AsyncClient(base_url=settings.mock_api_url) as client:
#         response = await client.get("/api/v1/stats/summary")
#         response.raise_for_status()
#         return StatsSummary(**response.json())
