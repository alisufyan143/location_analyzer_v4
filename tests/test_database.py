"""
Tests for database engine, ORM models, and repository layer.

All tests use SQLite in-memory — no external database required.
"""

import pytest
from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from location_analyzer.data.database import Base, create_db_engine, create_session_factory, init_db
from location_analyzer.data.models import (
    Postcode, Demographics, SalesData, GoogleMapsPlace,
    CrystalEthnicity, CrystalRestaurant, CrystalPub,
    CrystalIncome, CrystalTransport, CrystalOccupation, University,
)
from location_analyzer.data.repository import PostcodeRepository
from location_analyzer.exceptions import PostcodeNotFoundError


# ─── Fixtures ───────────────────────────────────────────────


@pytest.fixture
def engine():
    """Create an in-memory SQLite engine for testing."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def session(engine):
    """Create a database session for testing, rolled back after each test."""
    SessionLocal = sessionmaker(bind=engine)
    sess = SessionLocal()
    yield sess
    sess.rollback()
    sess.close()


@pytest.fixture
def repo(session):
    """Create a PostcodeRepository instance for testing."""
    return PostcodeRepository(session)


# ─── Database Engine Tests ──────────────────────────────────


class TestDatabaseEngine:
    """Tests for database engine creation."""

    def test_sqlite_engine_connects(self, engine):
        """SQLite in-memory engine should connect and respond."""
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

    def test_tables_created(self, engine):
        """All ORM model tables should be created."""
        table_names = Base.metadata.tables.keys()
        expected = {
            "postcodes", "postcode_area_demographics",
            "crystal_ethnicity", "crystal_restaurants", "crystal_pubs",
            "crystal_income", "crystal_transport", "crystal_occupation",
            "gmaps_universities", "google_maps_places", "sales_data",
        }
        assert expected == set(table_names)

    def test_init_db_with_explicit_engine(self, engine):
        """init_db should not fail when called on an already-initialized engine."""
        # Should be idempotent
        init_db(engine=engine)

    def test_create_engine_with_url(self):
        """create_db_engine should work with an explicit SQLite URL."""
        eng = create_db_engine("sqlite:///:memory:")
        with eng.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1


# ─── ORM Model Tests ───────────────────────────────────────


class TestPostcodeModel:
    """Tests for the Postcode ORM model."""

    def test_create_postcode(self, session):
        """Should create a postcode record."""
        pc = Postcode(postcode="SW1A 1AA", outercode="SW1A", radius=1.6)
        session.add(pc)
        session.flush()

        result = session.get(Postcode, "SW1A 1AA")
        assert result is not None
        assert result.outercode == "SW1A"
        assert result.radius == 1.6

    def test_postcode_repr(self):
        """Repr should show postcode and prediction."""
        pc = Postcode(postcode="E1 6AN", prediction=1250.5)
        assert "E1 6AN" in repr(pc)

    def test_postcode_with_demographics(self, session):
        """Postcode should have a demographics relationship."""
        pc = Postcode(postcode="HA1 2TB", outercode="HA1")
        session.add(pc)
        session.flush()

        demo = Demographics(postcode="HA1 2TB", population=53000, households=22000)
        session.add(demo)
        session.flush()

        assert pc.demographics is not None
        assert pc.demographics.population == 53000


class TestDemographicsModel:
    """Tests for the Demographics ORM model."""

    def test_create_demographics(self, session):
        """Should create a demographics record linked to a postcode."""
        session.add(Postcode(postcode="E14 5AB", outercode="E14"))
        session.flush()

        demo = Demographics(
            postcode="E14 5AB",
            population=45000,
            households=18000,
            avg_household_income=52000,
            unemployment_rate=0.05,
            working=72.5,
            unemployed=5.2,
            ab=35.0,
            c1_c2=40.0,
            de=25.0,
            white=60.0,
            non_white=40.0,
        )
        session.add(demo)
        session.flush()

        result = session.get(Demographics, demo.id)
        assert result.population == 45000
        assert result.avg_household_income == 52000


class TestCrystalModels:
    """Tests for CrystalRoof data models."""

    def test_crystal_ethnicity(self, session):
        """Should store ethnicity as JSON."""
        session.add(Postcode(postcode="SE1 7PB", outercode="SE1"))
        session.flush()

        eth = CrystalEthnicity(
            postcode="SE1 7PB",
            ethnicity={"white": 55.2, "asian": 20.1, "black": 15.3}
        )
        session.add(eth)
        session.flush()

        result = session.get(CrystalEthnicity, "SE1 7PB")
        assert result.ethnicity["white"] == 55.2
        assert result.ethnicity["asian"] == 20.1

    def test_crystal_restaurants(self, session):
        """Should store restaurant data as JSON."""
        session.add(Postcode(postcode="W1D 3AF", outercode="W1D"))
        session.flush()

        rest = CrystalRestaurant(
            postcode="W1D 3AF",
            restaurants={"count": 45, "types": ["indian", "chinese", "italian"]}
        )
        session.add(rest)
        session.flush()

        result = session.query(CrystalRestaurant).filter_by(postcode="W1D 3AF").one()
        assert result.restaurants["count"] == 45

    def test_crystal_transport(self, session):
        """Should store transport data as JSON."""
        session.add(Postcode(postcode="EC2R 8AH", outercode="EC2R"))
        session.flush()

        transport = CrystalTransport(
            postcode="EC2R 8AH",
            transport={"nearest_station": "Bank", "distance_km": 0.3}
        )
        session.add(transport)
        session.flush()

        result = session.get(CrystalTransport, "EC2R 8AH")
        assert result.transport["nearest_station"] == "Bank"


class TestSalesModel:
    """Tests for the SalesData model."""

    def test_create_sales_record(self, session):
        """Should create a sales record."""
        sale = SalesData(
            branch_name="Rio's Piri Piri - Croydon",
            postcode="CR0 1NA",
            source="Rios",
            date=datetime(2025, 1, 15),
            day_of_week="Wed",
            total_sale=585.31,
        )
        session.add(sale)
        session.flush()

        assert sale.id is not None
        assert sale.total_sale == 585.31

    def test_sales_repr(self):
        """Sales repr should include branch and sale amount."""
        s = SalesData(branch_name="Test Branch", total_sale=100.0)
        assert "Test Branch" in repr(s)


# ─── Repository Tests ──────────────────────────────────────


class TestPostcodeRepository:
    """Tests for the PostcodeRepository CRUD layer."""

    def test_upsert_new_postcode(self, repo, session):
        """Should insert a new postcode."""
        pc = repo.upsert_postcode("SW1A 1AA", radius=1.6, address="Buckingham Palace")
        session.commit()

        result = repo.get_postcode("SW1A 1AA")
        assert result is not None
        assert result.radius == 1.6
        assert result.outercode == "SW1A"

    def test_upsert_existing_postcode(self, repo, session):
        """Should update an existing postcode without creating a duplicate."""
        repo.upsert_postcode("E1 6AN", radius=1.0)
        session.commit()

        repo.upsert_postcode("E1 6AN", radius=2.0, prediction=1500.0)
        session.commit()

        result = repo.get_postcode("E1 6AN")
        assert result.radius == 2.0
        assert result.prediction == 1500.0

    def test_postcode_exists(self, repo, session):
        """Should check if a postcode exists."""
        assert repo.postcode_exists("FAKE") is False

        repo.upsert_postcode("SW1A 1AA")
        session.commit()
        assert repo.postcode_exists("SW1A 1AA") is True

    def test_list_postcodes(self, repo, session):
        """Should list postcodes with pagination."""
        for code in ["A1 1AA", "B2 2BB", "C3 3CC"]:
            repo.upsert_postcode(code)
        session.commit()

        result = repo.list_postcodes(limit=2)
        assert len(result) == 2

    def test_delete_postcode(self, repo, session):
        """Should delete a postcode and cascade to related data."""
        repo.upsert_postcode("DEL 1ET")
        repo.upsert_demographics("DEL 1ET", population=10000)
        session.commit()

        assert repo.delete_postcode("DEL 1ET") is True
        assert repo.get_postcode("DEL 1ET") is None
        assert repo.get_demographics("DEL 1ET") is None

    def test_delete_nonexistent_postcode(self, repo):
        """Should return False for nonexistent postcode."""
        assert repo.delete_postcode("NOPE") is False


class TestDemographicsRepository:
    """Tests for demographics CRUD operations."""

    def test_upsert_demographics(self, repo, session):
        """Should insert demographics and auto-create the postcode."""
        repo.upsert_demographics(
            "HA1 2TB",
            population=53000,
            households=22000,
            avg_household_income=35000,
        )
        session.commit()

        # Postcode should exist (auto-created)
        assert repo.postcode_exists("HA1 2TB")

        demo = repo.get_demographics("HA1 2TB")
        assert demo.population == 53000
        assert demo.avg_household_income == 35000

    def test_update_demographics(self, repo, session):
        """Should update existing demographics."""
        repo.upsert_demographics("HA1 2TB", population=53000)
        session.commit()

        repo.upsert_demographics("HA1 2TB", population=55000, unemployment_rate=0.04)
        session.commit()

        demo = repo.get_demographics("HA1 2TB")
        assert demo.population == 55000
        assert demo.unemployment_rate == 0.04


class TestCrystalRepository:
    """Tests for CrystalRoof data CRUD operations."""

    def test_upsert_crystal_ethnicity(self, repo, session):
        """Should upsert ethnicity data."""
        data = {"white": 60.0, "asian": 25.0, "black": 15.0}
        repo.upsert_crystal_ethnicity("E1 6AN", data)
        session.commit()

        result = repo.get_crystal_ethnicity("E1 6AN")
        assert result.ethnicity["white"] == 60.0

    def test_upsert_crystal_restaurants(self, repo, session):
        """Should upsert restaurant data."""
        data = {"count": 30, "top": ["Nando's", "KFC"]}
        repo.upsert_crystal_restaurants("W1D 3AF", data)
        session.commit()

        result = repo.get_crystal_restaurants("W1D 3AF")
        assert result.restaurants["count"] == 30

    def test_upsert_crystal_pubs(self, repo, session):
        """Should upsert pub data."""
        data = {"count": 12}
        repo.upsert_crystal_pubs("EC1A 1BB", data)
        session.commit()

        result = repo.get_crystal_pubs("EC1A 1BB")
        assert result.pubs["count"] == 12

    def test_upsert_crystal_income(self, repo, session):
        """Should upsert income data."""
        data = {"median": 45000, "mean": 52000}
        repo.upsert_crystal_income("SW1A 1AA", data)
        session.commit()

        result = repo.get_crystal_income("SW1A 1AA")
        assert result.income["median"] == 45000

    def test_upsert_crystal_transport(self, repo, session):
        """Should upsert transport data."""
        data = {"nearest_station": "Victoria", "distance_km": 0.5}
        repo.upsert_crystal_transport("SW1V 1QT", data)
        session.commit()

        result = repo.get_crystal_transport("SW1V 1QT")
        assert result.transport["nearest_station"] == "Victoria"

    def test_upsert_crystal_occupation(self, repo, session):
        """Should upsert occupation data."""
        data = {"professional": 45, "manual": 20}
        repo.upsert_crystal_occupation("N1 9GU", data)
        session.commit()

        result = repo.get_crystal_occupation("N1 9GU")
        assert result.occupation["professional"] == 45

    def test_update_existing_crystal(self, repo, session):
        """Should update existing crystal data, not create duplicate."""
        repo.upsert_crystal_ethnicity("E1 6AN", {"white": 60.0})
        session.commit()

        repo.upsert_crystal_ethnicity("E1 6AN", {"white": 55.0, "asian": 30.0})
        session.commit()

        result = repo.get_crystal_ethnicity("E1 6AN")
        assert result.ethnicity["white"] == 55.0
        assert result.ethnicity["asian"] == 30.0


class TestUniversityRepository:
    """Tests for university data."""

    def test_upsert_universities(self, repo, session):
        """Should upsert university data."""
        data = {"count": 3, "names": ["UCL", "KCL", "Imperial"]}
        repo.upsert_universities("WC1E 6BT", data)
        session.commit()

        result = repo.get_universities("WC1E 6BT")
        assert result.universities["count"] == 3


class TestGoogleMapsRepository:
    """Tests for Google Maps place data."""

    def test_add_place(self, repo, session):
        """Should add a Google Maps place."""
        place = repo.add_place(
            "E1 6AN",
            name="Nando's Whitechapel",
            address="123 High St",
            reviews_count=500,
            reviews_average=4.2,
            place_type="restaurant",
        )
        session.commit()

        assert place.id is not None
        assert place.name == "Nando's Whitechapel"

    def test_get_places(self, repo, session):
        """Should return all places for a postcode."""
        repo.add_place("E1 6AN", name="Place A", place_type="restaurant")
        repo.add_place("E1 6AN", name="Place B", place_type="cafe")
        session.commit()

        places = repo.get_places("E1 6AN")
        assert len(places) == 2


class TestSalesRepository:
    """Tests for sales data operations."""

    def test_add_sales_record(self, repo, session):
        """Should add a sales record."""
        record = repo.add_sales_record(
            branch_name="Rio's Piri Piri - Croydon",
            date=datetime(2025, 1, 15),
            total_sale=585.31,
            postcode="CR0 1NA",
            source="Rios",
        )
        session.commit()

        assert record.id is not None
        assert record.outercode == "CR0"

    def test_get_sales_by_branch(self, repo, session):
        """Should filter sales by branch and date range."""
        for day in [10, 15, 20]:
            repo.add_sales_record(
                branch_name="Test Branch",
                date=datetime(2025, 1, day),
                total_sale=100.0 * day,
            )
        session.commit()

        all_sales = repo.get_sales_by_branch("Test Branch")
        assert len(all_sales) == 3

        filtered = repo.get_sales_by_branch(
            "Test Branch",
            start_date=datetime(2025, 1, 12),
            end_date=datetime(2025, 1, 18),
        )
        assert len(filtered) == 1
        assert filtered[0].total_sale == 1500.0

    def test_count_sales(self, repo, session):
        """Should count total sales records."""
        assert repo.count_sales() == 0
        repo.add_sales_record("Branch A", datetime(2025, 1, 1), 100.0)
        repo.add_sales_record("Branch B", datetime(2025, 1, 2), 200.0)
        session.commit()

        assert repo.count_sales() == 2


class TestAggregateQueries:
    """Tests for aggregate/combined queries."""

    def test_get_full_postcode_data(self, repo, session):
        """Should return all data for a postcode across tables."""
        repo.upsert_postcode("E1 6AN", radius=1.6, prediction=1200.0)
        repo.upsert_demographics("E1 6AN", population=50000, households=20000)
        repo.upsert_crystal_ethnicity("E1 6AN", {"white": 55.0})
        repo.upsert_crystal_restaurants("E1 6AN", {"count": 30})
        repo.add_place("E1 6AN", name="Test Place", place_type="restaurant")
        session.commit()

        data = repo.get_full_postcode_data("E1 6AN")
        assert data["postcode"]["prediction"] == 1200.0
        assert data["demographics"]["population"] == 50000
        assert data["crystal"]["ethnicity"]["white"] == 55.0
        assert data["crystal"]["restaurants"]["count"] == 30
        assert len(data["places"]) == 1

    def test_get_full_postcode_data_not_found(self, repo):
        """Should raise PostcodeNotFoundError for missing postcode."""
        with pytest.raises(PostcodeNotFoundError):
            repo.get_full_postcode_data("ZZZZ")

    def test_get_full_postcode_data_partial(self, repo, session):
        """Should return None for missing optional data."""
        repo.upsert_postcode("N1 9GU")
        session.commit()

        data = repo.get_full_postcode_data("N1 9GU")
        assert data["postcode"]["postcode"] == "N1 9GU"
        assert data["demographics"] is None
        assert data["crystal"]["ethnicity"] is None
        assert data["places"] == []
