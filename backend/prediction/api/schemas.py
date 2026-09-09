from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    site_id: str = Field(examples=["SITE001"])
    prediction_timestamp: datetime
    target_timestamp: datetime
    predicted_consumption_kw: float = Field(examples=[12.34])
    model_version: str = Field(examples=["3"])


class ForecastPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    horizon_hours: int = Field(examples=[1])
    target_timestamp: datetime
    predicted_consumption_kw: float = Field(examples=[6.10])


class ForecastResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    site_id: str = Field(examples=["SITE001"])
    generated_at: datetime = Field(
        description="Moment réel où l'API a calculé le forecast (horloge système)."
    )
    base_timestamp: datetime = Field(
        description="Dernière mesure réellement utilisée pour construire les features. "
        "Peut être postérieure à `generated_at` avec un dataset simulé/historique."
    )
    horizon_hours: int = Field(examples=[24], description="Horizon demandé (1 à 48).")
    model_version: str = Field(examples=["7"])
    predictions: list[ForecastPoint]
