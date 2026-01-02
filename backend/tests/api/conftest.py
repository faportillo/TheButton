import os

os.environ["REDUCER_ENV"] = "dev"
os.environ["REDUCER_DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REDUCER_KAFKA_BROKER_URL"] = "localhost:9092"
os.environ["KAFKA_BROKER_URL"] = "localhost:9092"
os.environ["REDUCER_KAFKA_API_KEY"] = "test-key"
os.environ["KAFKA_API_KEY"] = "test-key"
os.environ["REDUCER_KAFKA_API_SECRET"] = "test-secret"
os.environ["KAFKA_API_SECRET"] = "test-secret"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.models import Base
import api.state as state


@pytest.fixture
def sqlite_engine(tmp_path):
    """Create a temporary SQLite database engine for testing."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def patch_state_db(sqlite_engine, monkeypatch):
    """Patch the state module to use the SQLite test database."""
    Base.metadata.create_all(sqlite_engine)
    monkeypatch.setattr(state, "engine", sqlite_engine, raising=True)
    monkeypatch.setattr(
        state, "SessionLocal", sessionmaker(bind=sqlite_engine), raising=True
    )

