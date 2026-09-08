from pydantic import BaseModel, Field

class Site(BaseModel):
    site_id: str = Field(examples=["SITE001"])
    site_type: str = Field(examples=["office"])
    site_name: str = Field(examples=["Bureau Paris La Défense"])
    location: str = Field(examples=["Paris, France"])
    capacity_kw: int = Field(examples=[200])
    status: str = Field(examples=["active"])
