from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Boolean, Float, Text
from typing import Optional

class Base(DeclarativeBase):
    pass

class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rating_avg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    skills: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # comma-separated for MVP
    price_band: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # MVP (we’ll move to PostGIS geometry later)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
