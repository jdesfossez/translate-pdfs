"""Database setup and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import get_settings
from src.models.job import Base

settings = get_settings()

# Create engine
engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    # SQLite specific settings
    connect_args=(
        {"check_same_thread": False} if "sqlite" in settings.database_url else {}
    ),
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables():
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
