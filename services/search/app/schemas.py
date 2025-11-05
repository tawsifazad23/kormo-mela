from pydantic import BaseModel, Field
from typing import Optional, List

class ProviderHit(BaseModel):
    id: int
    name: str
    verified: bool
    rating_avg: Optional[float]
    skills: Optional[str]
    price_band: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    distance_km: float

class SearchRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_km: float = Field(gt=0, le=50)  # cap to 50km for MVP
    limit: int = Field(default=20, ge=1, le=100)

class SearchResponse(BaseModel):
    count: int
    hits: List[ProviderHit]
