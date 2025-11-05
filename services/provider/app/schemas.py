from pydantic import BaseModel, Field
from typing import Optional

class ProviderCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    verified: bool = False
    rating_avg: Optional[float] = None
    skills: Optional[str] = None  # e.g. "driver,english"
    price_band: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None

class ProviderOut(BaseModel):
    id: int
    name: str
    verified: bool
    rating_avg: Optional[float]
    skills: Optional[str]
    price_band: Optional[str]
    lat: Optional[float]
    lon: Optional[float]

    class Config:
        from_attributes = True
