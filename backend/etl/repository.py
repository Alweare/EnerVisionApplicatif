from datetime import datetime

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
