from workeringestion import repository
from workeringestion.schemas import EnergyReading


class SiteNotFoundError(Exception):
    def __init__(self, site_id: str):
        self.site_id = site_id
        super().__init__(f"Site '{site_id}' introuvable")


async def get_current_reading(site_id: str) -> EnergyReading:
    reading = await repository.get_current_reading(site_id)
    if reading is None:
        raise SiteNotFoundError(site_id)
    return reading
