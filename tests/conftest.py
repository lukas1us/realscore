"""
Pytest fixtures pro DB smoke testy.

Vytvoří dedikovanou testovací DB 'realscoreCZ_test', spustí create_all
a po každém testu smaže všechna data (TRUNCATE). DB samotná zůstane mezi testy
pro rychlost.

Požaduje běžící PostgreSQL na localhost:5432 (stejně jako prod).
"""

import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Základní connection string — postgres superuser pro vytvoření DB
_BASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/realscoreCZ_test",
)
_ADMIN_URL = _BASE_URL.rsplit("/", 1)[0] + "/postgres"
_DB_NAME = "realscoreCZ_test"


def _ensure_test_db_exists():
    """Vytvoří testovací DB pokud neexistuje."""
    engine = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": _DB_NAME},
        ).fetchone()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{_DB_NAME}"'))
    engine.dispose()


@pytest.fixture(scope="session")
def db_engine():
    """Vytvoří engine + schema jednou pro celou session."""
    _ensure_test_db_exists()

    engine = create_engine(_BASE_URL, pool_pre_ping=True)

    # Vytvoř tabulky podle SQLAlchemy modelů
    from backend import models  # noqa: F401 – registruje modely
    from backend.database import Base
    Base.metadata.create_all(bind=engine)

    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine):
    """Session fixture — po každém testu smaže data ze všech tabulek."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    # Smaž data, ale zachovej strukturu
    session.execute(text("TRUNCATE properties, price_benchmarks RESTART IDENTITY CASCADE"))
    session.commit()
    session.close()
