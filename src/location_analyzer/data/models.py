"""
SQLAlchemy ORM models for the Location Analyzer.

Maps directly from the old project's MySQL schema (connector.py)
to a clean, type-safe SQLAlchemy ORM.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Integer, Float, Text, DateTime, Boolean, JSON,
    ForeignKey, Index, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from location_analyzer.data.database import Base


# --- Core Tables ---


class Postcode(Base):
    """
    Core postcode record. Format matches pipeline: postcode normalized upper + strip
    (e.g. "SW1A 1AA"), outercode = first part (e.g. "SW1A"). prediction/min/max in GBP.
    """
    __tablename__ = "postcodes"

    postcode: Mapped[str] = mapped_column(String(10), primary_key=True)
    outercode: Mapped[Optional[str]] = mapped_column(String(5), index=True)
    radius: Mapped[Optional[float]] = mapped_column(Float)
    address: Mapped[Optional[str]] = mapped_column(String(255))
    prediction: Mapped[Optional[float]] = mapped_column(Float)
    min_prediction: Mapped[Optional[float]] = mapped_column(Float)
    max_prediction: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    demographics: Mapped[Optional["Demographics"]] = relationship(back_populates="postcode_ref", cascade="all, delete-orphan")
    crystal_ethnicity: Mapped[Optional["CrystalEthnicity"]] = relationship(back_populates="postcode_ref", cascade="all, delete-orphan")
    crystal_restaurants: Mapped[Optional["CrystalRestaurant"]] = relationship(back_populates="postcode_ref", cascade="all, delete-orphan")
    crystal_pubs: Mapped[Optional["CrystalPub"]] = relationship(back_populates="postcode_ref", cascade="all, delete-orphan")
    crystal_income: Mapped[Optional["CrystalIncome"]] = relationship(back_populates="postcode_ref", cascade="all, delete-orphan")
    crystal_transport: Mapped[Optional["CrystalTransport"]] = relationship(back_populates="postcode_ref", cascade="all, delete-orphan")
    crystal_occupation: Mapped[Optional["CrystalOccupation"]] = relationship(back_populates="postcode_ref", cascade="all, delete-orphan")
    universities: Mapped[Optional["University"]] = relationship(back_populates="postcode_ref", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Postcode(postcode='{self.postcode}', prediction={self.prediction})>"


# --- Demographics (Nomis API + Doogal; DemographicsScraper) ---


class Demographics(Base):
    """
    Postcode demographics from DemographicsScraper (Nomis Census 2021 + Doogal).

    Column types and format match scraper output exactly:
    - population, households: int (counts; 0 on failure)
    - avg_household_income: float (GBP; from Doogal, int at source)
    - unemployment_rate, working, unemployed, ab, c1_c2, de, white, non_white:
      float, 0.0–1.0 (fraction, not percentage; matches ML training)
    - postcode: str, normalized upper + strip, max 8 chars (UK)
    """
    __tablename__ = "postcode_area_demographics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    postcode: Mapped[str] = mapped_column(String(10), ForeignKey("postcodes.postcode"), unique=True)
    population: Mapped[Optional[int]] = mapped_column(Integer)
    households: Mapped[Optional[int]] = mapped_column(Integer)
    avg_household_income: Mapped[Optional[float]] = mapped_column(Float)
    unemployment_rate: Mapped[Optional[float]] = mapped_column(Float)
    working: Mapped[Optional[float]] = mapped_column(Float)
    unemployed: Mapped[Optional[float]] = mapped_column(Float)
    ab: Mapped[Optional[float]] = mapped_column(Float)
    c1_c2: Mapped[Optional[float]] = mapped_column(Float)
    de: Mapped[Optional[float]] = mapped_column(Float)
    white: Mapped[Optional[float]] = mapped_column(Float)
    non_white: Mapped[Optional[float]] = mapped_column(Float)

    # Relationship
    postcode_ref: Mapped["Postcode"] = relationship(back_populates="demographics")

    def __repr__(self) -> str:
        return f"<Demographics(postcode='{self.postcode}', pop={self.population})>"


# --- CrystalRoof Data ---


class CrystalEthnicity(Base):
    """CrystalRoof ethnicity breakdown (stored as JSON)."""
    __tablename__ = "crystal_ethnicity"

    postcode: Mapped[str] = mapped_column(String(10), ForeignKey("postcodes.postcode"), primary_key=True)
    ethnicity: Mapped[Optional[dict]] = mapped_column(JSON)
    postcode_ref: Mapped["Postcode"] = relationship(back_populates="crystal_ethnicity")


class CrystalRestaurant(Base):
    """CrystalRoof nearby restaurants (stored as JSON)."""
    __tablename__ = "crystal_restaurants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    postcode: Mapped[str] = mapped_column(String(10), ForeignKey("postcodes.postcode"), unique=True)
    restaurants: Mapped[Optional[dict]] = mapped_column(JSON)
    postcode_ref: Mapped["Postcode"] = relationship(back_populates="crystal_restaurants")


class CrystalPub(Base):
    """CrystalRoof nearby pubs (stored as JSON)."""
    __tablename__ = "crystal_pubs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    postcode: Mapped[str] = mapped_column(String(10), ForeignKey("postcodes.postcode"), unique=True)
    pubs: Mapped[Optional[dict]] = mapped_column(JSON)
    postcode_ref: Mapped["Postcode"] = relationship(back_populates="crystal_pubs")


class CrystalIncome(Base):
    """CrystalRoof household income data (stored as JSON)."""
    __tablename__ = "crystal_income"

    postcode: Mapped[str] = mapped_column(String(10), ForeignKey("postcodes.postcode"), primary_key=True)
    income: Mapped[Optional[dict]] = mapped_column(JSON)
    postcode_ref: Mapped["Postcode"] = relationship(back_populates="crystal_income")


class CrystalTransport(Base):
    """
    Transport data from CrystalRoofScraper, flattened for ML.

    transport JSON keys (match pipeline _flatten_crystalroof output):
    - Transport_Accessibility_Score: int (1–10)
    - Nearby_Station_Count: int
    - Distance_to_Nearest_Station: float (miles)
    - Nearest_Station_Type: str (e.g. "Underground", "National Rail")
    """
    __tablename__ = "crystal_transport"

    postcode: Mapped[str] = mapped_column(String(10), ForeignKey("postcodes.postcode"), primary_key=True)
    transport: Mapped[Optional[dict]] = mapped_column(JSON)
    postcode_ref: Mapped["Postcode"] = relationship(back_populates="crystal_transport")


class CrystalOccupation(Base):
    """CrystalRoof occupation data (stored as JSON)."""
    __tablename__ = "crystal_occupation"

    postcode: Mapped[str] = mapped_column(String(10), ForeignKey("postcodes.postcode"), primary_key=True)
    occupation: Mapped[Optional[dict]] = mapped_column(JSON)
    postcode_ref: Mapped["Postcode"] = relationship(back_populates="crystal_occupation")


# --- Google Maps ---


class University(Base):
    """Google Maps university data (stored as JSON)."""
    __tablename__ = "gmaps_universities"

    postcode: Mapped[str] = mapped_column(String(10), ForeignKey("postcodes.postcode"), primary_key=True)
    universities: Mapped[Optional[dict]] = mapped_column(JSON)
    postcode_ref: Mapped["Postcode"] = relationship(back_populates="universities")


class GoogleMapsPlace(Base):
    """Individual Google Maps place/business record."""
    __tablename__ = "google_maps_places"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    postcode: Mapped[str] = mapped_column(String(10), ForeignKey("postcodes.postcode"), index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    address: Mapped[Optional[str]] = mapped_column(String(500))
    website: Mapped[Optional[str]] = mapped_column(String(500))
    phone_number: Mapped[Optional[str]] = mapped_column(String(50))
    reviews_count: Mapped[Optional[int]] = mapped_column(Integer)
    reviews_average: Mapped[Optional[float]] = mapped_column(Float)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    url: Mapped[Optional[str]] = mapped_column(Text)
    place_type: Mapped[Optional[str]] = mapped_column(String(100))

    __table_args__ = (Index("ix_gmaps_postcode_name", "postcode", "name"),)


# --- Sales Data (for ML training) ---


class SalesData(Base):
    """
    Sales records for ML model training.

    Schema matches: cleaned_dataset.xlsx (73K rows)
    """
    __tablename__ = "sales_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    branch_name: Mapped[str] = mapped_column(String(255), index=True)
    postcode: Mapped[Optional[str]] = mapped_column(String(10), index=True)
    outercode: Mapped[Optional[str]] = mapped_column(String(5))
    source: Mapped[Optional[str]] = mapped_column(String(100))  # Pepes, Rios, Maemes, etc.
    shopname: Mapped[Optional[str]] = mapped_column(String(255))
    date: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    day_of_week: Mapped[Optional[str]] = mapped_column(String(10))
    total_sale: Mapped[Optional[float]] = mapped_column(Float)

    __table_args__ = (Index("ix_sales_branch_date", "branch_name", "date"),)

    def __repr__(self) -> str:
        return f"<SalesData(branch='{self.branch_name}', date={self.date}, sale={self.total_sale})>"
