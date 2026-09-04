import os

BACKEND_URL = os.environ["BACKEND_URL"]

MOCK_CURRENT = {
    "consumption_kw": 87.34,
    "temperature_celsius": 22.1,
    "data_quality": "good",
}

MOCK_HISTORY = [
    {"measurement_date": "2026-09-02T10:00:00", "consumption_kw": 80.1},
    {"measurement_date": "2026-09-02T11:00:00", "consumption_kw": 85.4},
    {"measurement_date": "2026-09-02T12:00:00", "consumption_kw": 87.34},
]

def get_current_measurement(site_id: str) -> dict:
        return MOCK_CURRENT

def get_measurement_history(site_id: str) -> list[dict]:
        return MOCK_HISTORY