from backend.sites.schemas import Site

# Mock en mémoire en attendant le branchement sur la Mock API / la base de
# données via l'ETL. SITE001 et SITE002 sont repris tels quels de la doc
# Mock API ; SITE003 est complété par des valeurs plausibles (site_type,
# location, status) non documentées à ce jour.
_MOCK_SITES: list[Site] = [
    Site(
        site_id="SITE001",
        site_type="office",
        site_name="Bureau Paris La Défense",
        location="Paris, France",
        capacity_kw=200,
        status="active",
    ),
    Site(
        site_id="SITE002",
        site_type="factory",
        site_name="Usine Lyon Vénissieux",
        location="Lyon, France",
        capacity_kw=1000,
        status="active",
    ),
    Site(
        site_id="SITE003",
        site_type="datacenter",
        site_name="Data Center Marseille",
        location="Marseille, France",
        capacity_kw=800,
        status="active",
    ),
]


def list_sites() -> list[Site]:
    return _MOCK_SITES


def get_site(site_id: str) -> Site | None:
    return next((site for site in _MOCK_SITES if site.site_id == site_id), None)


# --- Pour plus tard : proxy vers la Mock API distante ---
# Une fois l'URL de la Mock API disponible (cf. core/config.py), remplacer
# list_sites/get_site ci-dessus par des appels HTTP, par ex avec httpx
# (à ajouter à requirements.txt) :
#
# import httpx
# from backend.core.config import settings
#
# async def list_sites() -> list[Site]:
#     async with httpx.AsyncClient(base_url=settings.mock_api_url) as client:
#         response = await client.get("/api/v1/sites")
#         response.raise_for_status()
#         return [Site(**item) for item in response.json()]
#
# async def get_site(site_id: str) -> Site | None:
#     async with httpx.AsyncClient(base_url=settings.mock_api_url) as client:
#         response = await client.get(f"/api/v1/sites/{site_id}")
#         if response.status_code == 404:
#             return None
#         response.raise_for_status()
#         return Site(**response.json())
