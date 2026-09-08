from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

RecommendationStatus = Literal["pending", "applied", "dismissed"]


class SiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    site_id: str = Field(examples=["SITE001"])
    site_type: str | None = Field(default=None, examples=["office"])
    site_name: str | None = Field(default=None, examples=["Bureau Paris La Défense"])
    location: str | None = Field(default=None, examples=["Paris, France"])
    capacity_kw: float | None = Field(default=None, examples=[200.0])
    status: str | None = Field(default=None, examples=["active"])


class SiteWithCurrentRead(SiteRead):
    """`SiteRead` enrichi de la dernière mesure connue du site."""
    current_consumption_kw: float | None = Field(default=None, examples=[104.47])
    data_quality: str | None = Field(default=None, examples=["good"])


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


class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recommendation_id: UUID
    site_id: str | None = Field(default=None, examples=["SITE001"])
    prediction_id: UUID
    rule_key: str | None = Field(default=None, examples=["peak_over_90pct_capacity"])
    action_type: str | None = Field(default=None, examples=["shift_load"])
    message: str | None = Field(
        default=None,
        examples=["Pic prévu à 18h00 : 190 kW (capacité 200 kW). Décaler les usages flexibles."],
    )
    estimated_gain_kw: float | None = Field(default=None, examples=[20.0])
    predicted_for: datetime | None = Field(
        default=None,
        examples=["2026-09-15T18:00:00"],
        description="Heure du pic visé",
    )
    status: RecommendationStatus = Field(examples=["pending"])
    created_at: datetime


class RecommendationStatusUpdate(BaseModel):
    status: RecommendationStatus = Field(examples=["applied"])

class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alert_id: str = Field(examples=["ALR-SITE002-1718458320"])
    site_id: str = Field(examples=["SITE002"])
    severity: str | None = Field(default=None, examples=["critical"])
    type: str | None = Field(default=None, examples=["spike"])
    message: str | None = Field(
        default=None, examples=["Pic de consommation détecté sur Usine Lyon Vénissieux"]
    )
    value: float | None = Field(default=None, examples=[812.5])
    threshold: float | None = Field(default=None, examples=[720.0])
    created_at: datetime
