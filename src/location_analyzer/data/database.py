"""
Database engine and session management.

Supports PostgreSQL (production) and SQLite (development) via DATABASE_URL.
Uses SQLAlchemy with connection pooling and health checks.
"""

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from sqlalchemy.pool import StaticPool

from location_analyzer.config import settings
from location_analyzer.logging_config import get_logger
from location_analyzer.exceptions import DatabaseConnectionError

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def _is_sqlite(url: str) -> bool:
    """Check if the database URL is SQLite."""
    return url.startswith("sqlite")


def create_db_engine(database_url: str | None = None):
    """
    Create a SQLAlchemy engine based on the database URL.

    Args:
        database_url: Override the URL from settings. Useful for testing.

    Returns:
        SQLAlchemy Engine instance
    """
    url = database_url or settings.database.url
    logger.info("Creating database engine — %s", "SQLite" if _is_sqlite(url) else "PostgreSQL")

    try:
        if _is_sqlite(url):
            # SQLite: use StaticPool for thread safety, enable WAL mode
            engine = create_engine(
                url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
                echo=False,
            )
            # Enable WAL mode and foreign keys for SQLite
            @event.listens_for(engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        else:
            # PostgreSQL: connection pooling
            engine = create_engine(
                url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,  # Health check before using connection
                echo=False,
            )

        # Verify connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection verified successfully")

        return engine

    except Exception as e:
        raise DatabaseConnectionError(
            message=f"Failed to connect to database: {e}",
            details={"url": url.split("@")[-1] if "@" in url else url},  # Hide credentials
        ) from e


def create_session_factory(engine=None) -> sessionmaker[Session]:
    """
    Create a session factory bound to the given engine.

    Args:
        engine: SQLAlchemy engine. If None, creates one from settings.

    Returns:
        Configured sessionmaker
    """
    if engine is None:
        engine = create_db_engine()
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db(engine=None) -> None:
    """
    Initialize the database — create all tables.

    Args:
        engine: SQLAlchemy engine. If None, creates one from settings.
    """
    if engine is None:
        engine = create_db_engine()

    # Import all models so they register with Base.metadata
    import location_analyzer.data.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")
