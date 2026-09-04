from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    site_id: str = Field(examples=["SITE001"])
    site_type: str | None = Field(default=None, examples=["office"])
    site_name: str | None = Field(default=None, examples=["Bureau Paris La Défense"])
    location: str | None = Field(default=None, examples=["Paris, France"])
    capacity_kw: float | None = Field(default=None, examples=[200.0])
    status: str | None = Field(default=None, examples=["active"])


class MeasurementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    measurement_id: UUID
    site_id: str = Field(examples=["SITE001"])
    measurement_date: datetime
    consumption_kw: float | None
    consumption_kwh: float | None
    voltage_v: float | None
    current_a: float | None
    power_factor: float | None
    temperature_celsius: float | None
    humidity_percent: float | None
    null_reason: list[str] | None
    data_quality: str = Field(examples=["good"])
    created_at: datetime | None
