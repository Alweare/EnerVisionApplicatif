from datetime import datetime, timedelta

from backend.etl.schemas import EnergyReading

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
