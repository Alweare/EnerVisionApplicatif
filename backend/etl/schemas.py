from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DataQuality = Literal["good", "partial", "degraded", "critical"]
SensorStatusValue = Literal["ok", "failing"]
OverallStatus = Literal["ok", "degraded", "critical"]
AlertSeverity = Literal["low", "medium", "high", "critical"]
AlertType = Literal["spike", "threshold", "anomaly", "outage", "sensor"]


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


class Alert(BaseModel):
    alert_id: str = Field(examples=["ALR-SITE002-1718458320"])
    timestamp: datetime
    site_id: str = Field(examples=["SITE002"])
    severity: AlertSeverity
    type: AlertType
    message: str
    value: float
    threshold: float


class SiteStat(BaseModel):
    site_id: str = Field(examples=["SITE001"])
    site_name: str = Field(examples=["Bureau Paris La Défense"])
    current_consumption_kw: float | None
    capacity_kw: int
    load_percent: float | None
    data_quality: DataQuality


class StatsSummary(BaseModel):
    timestamp: datetime
    total_sites: int
    total_consumption_kw: float
    total_capacity_kw: int
    average_load_percent: float
    has_incomplete_data: bool = Field(
        description="True si au moins un site a un data_quality 'critical'"
    )
    sites: list[SiteStat]
