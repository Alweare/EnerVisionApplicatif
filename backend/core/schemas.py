from pydantic import BaseModel, Field

class ErrorDetail(BaseModel):
    detail: str = Field(examples=["Site 'UNKNOWN' introuvable"])
