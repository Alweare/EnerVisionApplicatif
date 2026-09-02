from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DataQuality = Literal["good", "partial", "degraded", "critical"]
SensorStatusValue = Literal["ok", "failing"]
OverallStatus = Literal["ok", "degraded", "critical"]


class EnergyReading(BaseModel):
    timestamp: datetime
    site_id: str = Field(examples=["SITE001"])
    site_type: str = Field(examples=["office"])
    consumption_kw: float | None
    consumption_kwh: float | None
    voltage_v: float | None
    current_a: float | None
    power_factor: float | None
    temperature_celsius: float | None
    humidity_percent: float | None
    null_reasons: list[str] = Field(default_factory=list)
    data_quality: DataQuality


class SensorState(BaseModel):
    status: SensorStatusValue
    failing_until: datetime | None = Field(
        default=None, examples=["2024-06-15T14:33:05"]
    )


class SensorsBlock(BaseModel):
    consumption: SensorState
    electrical: SensorState
    temperature: SensorState
    humidity: SensorState
    network: SensorState


class SiteSensorsStatus(BaseModel):
    site_name: str = Field(examples=["Bureau Paris La Défense"])
    sensors: SensorsBlock
    overall: OverallStatus
