from datetime import datetime

from backend.workerIngestion import repository
from backend.workerIngestion.schemas import (
    Alert,
    EnergyReading,
    SimulateSpikeResult,
    Site,
    SiteSensorsStatus,
    SiteStat,
    StatsSummary,
)


class SiteNotFoundError(Exception):
    def __init__(self, site_id: str):
        self.site_id = site_id
        super().__init__(f"Site '{site_id}' introuvable")


async def list_sites() -> list[Site]:
    return await repository.list_sites()


async def get_site(site_id: str) -> Site:
    site = await repository.get_site(site_id)
    if site is None:
        raise SiteNotFoundError(site_id)
    return site


async def get_current_reading(site_id: str) -> EnergyReading:
    reading = await repository.get_current_reading(site_id)
    if reading is None:
        raise SiteNotFoundError(site_id)
    return reading


async def get_readings(
    site_id: str | None,
    start_time: datetime | None,
    end_time: datetime | None,
    limit: int,
) -> list[EnergyReading]:
    readings = await repository.get_readings(site_id, start_time, end_time, limit)
    if readings is None:
        raise SiteNotFoundError(site_id)
    return readings


async def get_sensors_status() -> dict[str, SiteSensorsStatus]:
    return await repository.get_sensors_status()


async def get_alerts(site_id: str | None = None, severity: str | None = None) -> list[Alert]:
    return await repository.list_alerts(site_id, severity)


async def get_stats_summary() -> StatsSummary:
    raw = await repository.get_stats_summary_raw()
    sites = [SiteStat(**item) for item in raw["sites"]]
    has_incomplete_data = any(site.data_quality == "critical" for site in sites)

    return StatsSummary(
        timestamp=raw["timestamp"],
        total_sites=raw["total_sites"],
        total_consumption_kw=raw["total_consumption_kw"],
        total_capacity_kw=raw["total_capacity_kw"],
        average_load_percent=raw["average_load_percent"],
        has_incomplete_data=has_incomplete_data,
        sites=sites,
    )


async def simulate_spike(site_id: str, duration_minutes: int) -> SimulateSpikeResult:
    result = await repository.simulate_spike(site_id, duration_minutes)
    if result is None:
        raise SiteNotFoundError(site_id)
    return SimulateSpikeResult(**result)
