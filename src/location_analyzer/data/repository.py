"""
Repository layer — clean CRUD operations for all data models.

Replaces the old connector.py's 17 raw-SQL methods with a single
PostcodeRepository class using SQLAlchemy ORM.
"""

from typing import Optional, Any
from datetime import datetime, timedelta

from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session, joinedload

from location_analyzer.config import settings
from location_analyzer.data.models import (
    Postcode,
    Demographics,
    CrystalEthnicity,
    CrystalRestaurant,
    CrystalPub,
    CrystalIncome,
    CrystalTransport,
    CrystalOccupation,
    University,
    GoogleMapsPlace,
    SalesData,
)
from location_analyzer.logging_config import get_logger
from location_analyzer.exceptions import PostcodeNotFoundError

logger = get_logger(__name__)


class PostcodeRepository:
    """
    All database operations for postcode data.

    Usage:
        session_factory = create_session_factory()
        with session_factory() as session:
            repo = PostcodeRepository(session)
            repo.upsert_postcode("SW1A 1AA", radius=1.6)
    """

    def __init__(self, session: Session):
        self.session = session

    # --- Postcode CRUD ---

    def upsert_postcode(
        self,
        postcode: str,
        radius: float | None = None,
        address: str | None = None,
        prediction: float | None = None,
        min_prediction: float | None = None,
        max_prediction: float | None = None,
    ) -> Postcode:
        """Insert or update a postcode record."""
        # Extract outercode (first part before space)
        outercode = postcode.strip().split()[0] if " " in postcode else postcode[:3]

        existing = self.session.get(Postcode, postcode)
        if existing:
            if radius is not None:
                existing.radius = radius
            if address is not None:
                existing.address = address
            if prediction is not None:
                existing.prediction = prediction
            if min_prediction is not None:
                existing.min_prediction = min_prediction
            if max_prediction is not None:
                existing.max_prediction = max_prediction
            self.session.flush()
            return existing

        pc = Postcode(
            postcode=postcode,
            outercode=outercode,
            radius=radius,
            address=address,
            prediction=prediction,
            min_prediction=min_prediction,
            max_prediction=max_prediction,
        )
        self.session.add(pc)
        self.session.flush()
        return pc

    def get_postcode(self, postcode: str) -> Optional[Postcode]:
        """Get a postcode record, or None if not found."""
        return self.session.get(Postcode, postcode)

    def postcode_exists(self, postcode: str) -> bool:
        """Check if a postcode exists in the database."""
        return self.session.get(Postcode, postcode) is not None

    def list_postcodes(self, limit: int = 100, offset: int = 0) -> list[Postcode]:
        """List all postcodes with pagination."""
        stmt = select(Postcode).order_by(Postcode.postcode).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def delete_postcode(self, postcode: str) -> bool:
        """Delete a postcode and all related data (cascade)."""
        pc = self.session.get(Postcode, postcode)
        if pc:
            self.session.delete(pc)
            self.session.flush()
            return True
        return False

    # --- Demographics CRUD ---

    def upsert_demographics(self, postcode: str, **kwargs) -> Demographics:
        """
        Insert or update demographics for a postcode.

        Args:
            postcode: The postcode to upsert demographics for.
            **kwargs: Any Demographics field (population, households,
                      avg_household_income, unemployment_rate, working,
                      unemployed, ab, c1_c2, de, white, non_white).
        """
        # Ensure the postcode exists first
        self.upsert_postcode(postcode)

        existing = self.session.execute(
            select(Demographics).where(Demographics.postcode == postcode)
        ).scalar_one_or_none()

        if existing:
            for key, value in kwargs.items():
                if hasattr(existing, key) and value is not None:
                    setattr(existing, key, value)
            self.session.flush()
            return existing

        demo = Demographics(postcode=postcode, **kwargs)
        self.session.add(demo)
        self.session.flush()
        return demo

    def get_demographics(self, postcode: str) -> Optional[Demographics]:
        """Get demographics for a postcode."""
        return self.session.execute(
            select(Demographics).where(Demographics.postcode == postcode)
        ).scalar_one_or_none()

    # --- Crystal Data CRUD (generic for all Crystal tables) ---

    def _upsert_crystal(self, model_class, postcode: str, field_name: str, data: dict) -> Any:
        """Generic upsert for any CrystalRoof table."""
        self.upsert_postcode(postcode)

        existing = self.session.get(model_class, postcode)
        if existing:
            setattr(existing, field_name, data)
            self.session.flush()
            return existing

        obj = model_class(postcode=postcode, **{field_name: data})
        self.session.add(obj)
        self.session.flush()
        return obj

    def _get_crystal(self, model_class, postcode: str) -> Optional[Any]:
        """Generic get for any CrystalRoof table."""
        return self.session.get(model_class, postcode)

    # Crystal convenience methods
    def upsert_crystal_ethnicity(self, postcode: str, data: dict) -> CrystalEthnicity:
        return self._upsert_crystal(CrystalEthnicity, postcode, "ethnicity", data)

    def get_crystal_ethnicity(self, postcode: str) -> Optional[CrystalEthnicity]:
        return self._get_crystal(CrystalEthnicity, postcode)

    def upsert_crystal_restaurants(self, postcode: str, data: dict) -> CrystalRestaurant:
        # CrystalRestaurant uses auto-increment id, not postcode as PK
        self.upsert_postcode(postcode)
        existing = self.session.execute(
            select(CrystalRestaurant).where(CrystalRestaurant.postcode == postcode)
        ).scalar_one_or_none()
        if existing:
            existing.restaurants = data
            self.session.flush()
            return existing
        obj = CrystalRestaurant(postcode=postcode, restaurants=data)
        self.session.add(obj)
        self.session.flush()
        return obj

    def get_crystal_restaurants(self, postcode: str) -> Optional[CrystalRestaurant]:
        return self.session.execute(
            select(CrystalRestaurant).where(CrystalRestaurant.postcode == postcode)
        ).scalar_one_or_none()

    def upsert_crystal_pubs(self, postcode: str, data: dict) -> CrystalPub:
        self.upsert_postcode(postcode)
        existing = self.session.execute(
            select(CrystalPub).where(CrystalPub.postcode == postcode)
        ).scalar_one_or_none()
        if existing:
            existing.pubs = data
            self.session.flush()
            return existing
        obj = CrystalPub(postcode=postcode, pubs=data)
        self.session.add(obj)
        self.session.flush()
        return obj

    def get_crystal_pubs(self, postcode: str) -> Optional[CrystalPub]:
        return self.session.execute(
            select(CrystalPub).where(CrystalPub.postcode == postcode)
        ).scalar_one_or_none()

    def upsert_crystal_income(self, postcode: str, data: dict) -> CrystalIncome:
        return self._upsert_crystal(CrystalIncome, postcode, "income", data)

    def get_crystal_income(self, postcode: str) -> Optional[CrystalIncome]:
        return self._get_crystal(CrystalIncome, postcode)

    def upsert_crystal_transport(self, postcode: str, data: dict) -> CrystalTransport:
        return self._upsert_crystal(CrystalTransport, postcode, "transport", data)

    def get_crystal_transport(self, postcode: str) -> Optional[CrystalTransport]:
        return self._get_crystal(CrystalTransport, postcode)

    def upsert_crystal_occupation(self, postcode: str, data: dict) -> CrystalOccupation:
        return self._upsert_crystal(CrystalOccupation, postcode, "occupation", data)

    def get_crystal_occupation(self, postcode: str) -> Optional[CrystalOccupation]:
        return self._get_crystal(CrystalOccupation, postcode)

    # --- Universities ---

    def upsert_universities(self, postcode: str, data: dict) -> University:
        return self._upsert_crystal(University, postcode, "universities", data)

    def get_universities(self, postcode: str) -> Optional[University]:
        return self._get_crystal(University, postcode)

    # --- Google Maps Places ---

    def add_place(self, postcode: str, **kwargs) -> GoogleMapsPlace:
        """Add a Google Maps place record."""
        self.upsert_postcode(postcode)
        place = GoogleMapsPlace(postcode=postcode, **kwargs)
        self.session.add(place)
        self.session.flush()
        return place

    def get_places(self, postcode: str) -> list[GoogleMapsPlace]:
        """Get all Google Maps places near a postcode."""
        stmt = select(GoogleMapsPlace).where(GoogleMapsPlace.postcode == postcode)
        return list(self.session.scalars(stmt))

    # --- Sales Data ---

    def add_sales_record(
        self,
        branch_name: str,
        date: datetime,
        total_sale: float,
        postcode: str | None = None,
        source: str | None = None,
        shopname: str | None = None,
        day_of_week: str | None = None,
    ) -> SalesData:
        """Add a single sales record."""
        outercode = postcode.strip().split()[0] if postcode and " " in postcode else None

        record = SalesData(
            branch_name=branch_name,
            date=date,
            total_sale=total_sale,
            postcode=postcode,
            outercode=outercode,
            source=source,
            shopname=shopname,
            day_of_week=day_of_week,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_sales_by_branch(
        self,
        branch_name: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[SalesData]:
        """Get sales records for a branch, optionally filtered by date range."""
        stmt = select(SalesData).where(SalesData.branch_name == branch_name)
        if start_date:
            stmt = stmt.where(SalesData.date >= start_date)
        if end_date:
            stmt = stmt.where(SalesData.date <= end_date)
        return list(self.session.scalars(stmt.order_by(SalesData.date)))

    def count_sales(self) -> int:
        """Count total sales records."""
        return self.session.scalar(select(func.count(SalesData.id))) or 0

    # --- Prediction feature helpers (single query, no N+1) ---

    DEMO_KEYS = (
        "population", "households", "avg_household_income", "unemployment_rate",
        "working", "unemployed", "ab", "c1_c2", "de", "white", "non_white",
    )
    TRANSPORT_KEYS = (
        "Transport_Accessibility_Score", "Nearby_Station_Count",
        "Distance_to_Nearest_Station", "Nearest_Station_Type",
    )

    def get_features_for_postcode(self, postcode: str) -> Optional[dict[str, Any]]:
        """
        Load postcode + demographics + transport in one query and return
        a feature dict matching the pipeline output (for ML). Returns None
        if demographics are missing (so caller should scrape).
        """
        stmt = (
            select(Postcode)
            .where(Postcode.postcode == postcode)
            .options(
                joinedload(Postcode.demographics),
                joinedload(Postcode.crystal_transport),
            )
        )
        pc = self.session.execute(stmt).unique().scalars().first()
        if not pc or not pc.demographics:
            return None

        # Expire stale cache entries based on TTL setting
        if pc.updated_at:
            age_days = (datetime.now() - pc.updated_at).days
            if age_days > settings.database.db_cache_ttl_days:
                logger.info("Cache for %s is %d days old (TTL=%d). Forcing re-scrape.", 
                            postcode, age_days, settings.database.db_cache_ttl_days)
                return None

        out = {
            "postcode": pc.postcode,
            "outercode": pc.outercode or (pc.postcode.split()[0] if " " in pc.postcode else pc.postcode[:3]),
        }
        d = pc.demographics
        for k in self.DEMO_KEYS:
            v = getattr(d, k, None)
            if v is not None:
                out["c1/c2" if k == "c1_c2" else "non-white" if k == "non_white" else k] = v

        ct = pc.crystal_transport
        if ct and ct.transport and isinstance(ct.transport, dict):
            for k, v in ct.transport.items():
                if k in self.TRANSPORT_KEYS and v is not None:
                    # Never return a placeholder 0 transport score to inference;
                    # the ML OrdinalEncoder does not accept category 0.
                    if k == "Transport_Accessibility_Score":
                        try:
                            score_int = int(float(v))
                        except (TypeError, ValueError):
                            continue
                        if score_int <= 0:
                            continue
                        out[k] = score_int
                        continue
                    out[k] = v

        # Legacy Poisoned Cache Failsafe: Ensure the data we loaded is actually valid
        demographics_valid = out.get("population", 0) > 0 and out.get("de") is not None
        if not demographics_valid:
            logger.warning("Found incomplete/poisoned data in DB for %s (Missing core demographics). Forcing re-scrape.", postcode)
            return None

        crystalroof_valid = pc.crystal_transport is not None and isinstance(pc.crystal_transport.transport, dict)
        if not crystalroof_valid:
            logger.warning("Found incomplete/poisoned data in DB for %s (Missing transport layer). Forcing re-scrape.", postcode)
            return None

        return out

    @staticmethod
    def _coerce_demographics_value(key: str, value: Any) -> Any:
        """Coerce scraper output to DB types (Demographics table)."""
        if value is None:
            return None
        if key in ("population", "households"):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return None
        if key in ("avg_household_income", "unemployment_rate", "working", "unemployed", "ab", "c1_c2", "de", "white", "non_white"):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        return value

    @staticmethod
    def _coerce_transport_value(key: str, value: Any) -> Any:
        """Coerce pipeline transport values to types expected by CrystalTransport JSON."""
        if value is None:
            return None
        if key in ("Transport_Accessibility_Score", "Nearby_Station_Count"):
            try:
                iv = int(float(value))
                # Score 0 means "missing" in scraper/pipeline terms; store NULL not 0.
                if key == "Transport_Accessibility_Score" and iv <= 0:
                    return None
                return iv
            except (TypeError, ValueError):
                return None
        if key == "Distance_to_Nearest_Station":
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        if key == "Nearest_Station_Type":
            return str(value) if value is not None else None
        return value

    def save_scraped_result(self, postcode: str, features: dict[str, Any], display_data: dict[str, Any] | None = None) -> None:
        """
        Persist a pipeline output dict (postcode + demographics + transport).
        Coerces types to match DB column types. Single transaction.
        """
        self.upsert_postcode(postcode)
        
        # 1. Demographics
        demo_kwargs = {}
        for k in self.DEMO_KEYS:
            key = "c1/c2" if k == "c1_c2" else "non-white" if k == "non_white" else k
            if key in features and features[key] is not None:
                v = self._coerce_demographics_value(k, features[key])
                if v is not None:
                    demo_kwargs[k] = v
        if demo_kwargs:
            self.upsert_demographics(postcode, **demo_kwargs)

        # 2. Crystal Tables (from display_data if provided, else fall back to flat features)
        dd = display_data or {}
        
        # Ethnicity
        if "ethnicity" in dd:
            self.upsert_crystal_ethnicity(postcode, dd["ethnicity"])
        
        # Restaurants
        if "amenities" in dd and "restaurants" in dd["amenities"]:
            self.upsert_crystal_restaurants(postcode, dd["amenities"]["restaurants"])
        
        # Pubs
        if "amenities" in dd and "pubs" in dd["amenities"]:
            self.upsert_crystal_pubs(postcode, dd["amenities"]["pubs"])
        
        # Income/Affluence
        if "affluence" in dd:
            self.upsert_crystal_income(postcode, dd["affluence"])
            
        # Occupation
        if "occupation" in dd:
            self.upsert_crystal_occupation(postcode, dd["occupation"])

        # Transport (Merge list + score)
        transport_data = dd.get("transport", {})
        # Ensure we keep the flat ML features if they aren't in the rich dict
        for k in self.TRANSPORT_KEYS:
            if k in features and features[k] is not None:
                v = self._coerce_transport_value(k, features[k])
                if v is not None:
                    transport_data[k] = v
        
        if transport_data:
            self.upsert_crystal_transport(postcode, transport_data)

    def get_display_data(self, postcode: str) -> dict[str, Any]:
        """
        Load all CrystalRoof tables for a postcode and return a dict 
        matching the scraper output format.
        """
        out = {}
        
        # Ethnicity
        eth = self.get_crystal_ethnicity(postcode)
        if eth: out["ethnicity"] = eth.ethnicity
        
        # Amenities
        out["amenities"] = {
            "restaurants": self._get_json_field(self.get_crystal_restaurants(postcode), "restaurants") or [],
            "pubs": self._get_json_field(self.get_crystal_pubs(postcode), "pubs") or [],
        }
        
        # Affluence
        inc = self.get_crystal_income(postcode)
        if inc: out["affluence"] = inc.income
        
        # Occupation
        occ = self.get_crystal_occupation(postcode)
        if occ: out["occupation"] = occ.occupation
        
        # Transport
        trans = self.get_crystal_transport(postcode)
        if trans: out["transport"] = trans.transport
        
        return out

    # --- Aggregate Queries ---

    def get_full_postcode_data(self, postcode: str) -> dict[str, Any]:
        """
        Get ALL data for a postcode across all tables.

        Returns a dict with keys: postcode, demographics, crystal, universities, places.
        Raises PostcodeNotFoundError if postcode doesn't exist.
        """
        pc = self.get_postcode(postcode)
        if not pc:
            raise PostcodeNotFoundError(postcode=postcode)

        return {
            "postcode": {
                "postcode": pc.postcode,
                "outercode": pc.outercode,
                "radius": pc.radius,
                "address": pc.address,
                "prediction": pc.prediction,
                "min_prediction": pc.min_prediction,
                "max_prediction": pc.max_prediction,
            },
            "demographics": self._model_to_dict(self.get_demographics(postcode)),
            "crystal": {
                "ethnicity": self._get_json_field(self.get_crystal_ethnicity(postcode), "ethnicity"),
                "restaurants": self._get_json_field(self.get_crystal_restaurants(postcode), "restaurants"),
                "pubs": self._get_json_field(self.get_crystal_pubs(postcode), "pubs"),
                "income": self._get_json_field(self.get_crystal_income(postcode), "income"),
                "transport": self._get_json_field(self.get_crystal_transport(postcode), "transport"),
                "occupation": self._get_json_field(self.get_crystal_occupation(postcode), "occupation"),
            },
            "universities": self._get_json_field(self.get_universities(postcode), "universities"),
            "places": [
                {
                    "name": p.name,
                    "address": p.address,
                    "reviews_count": p.reviews_count,
                    "reviews_average": p.reviews_average,
                    "place_type": p.place_type,
                }
                for p in self.get_places(postcode)
            ],
        }

    @staticmethod
    def _model_to_dict(obj) -> Optional[dict]:
        """Convert a model instance to dict, excluding internal fields."""
        if obj is None:
            return None
        data = {}
        for col in obj.__table__.columns:
            if col.name not in ("id",):
                data[col.name] = getattr(obj, col.name)
        return data

    @staticmethod
    def _get_json_field(obj, field_name: str) -> Optional[dict]:
        """Safely extract a JSON field from a model instance."""
        if obj is None:
            return None
        return getattr(obj, field_name, None)
