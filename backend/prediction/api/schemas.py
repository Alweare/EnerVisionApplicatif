from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    site_id: str = Field(examples=["SITE001"])
    prediction_timestamp: datetime
    target_timestamp: datetime
    predicted_consumption_kw: float = Field(examples=[12.34])
    model_version: str = Field(examples=["3"])
