import os

os.environ["REDUCER_ENV"] = "dev"
os.environ["REDUCER_DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"  # also set alias without prefix
os.environ["REDUCER_KAFKA_BROKER_URL"] = "localhost:9092"
os.environ["KAFKA_BROKER_URL"] = "localhost:9092"  # also set alias without prefix
os.environ["REDUCER_KAFKA_API_KEY"] = "test-key"
os.environ["KAFKA_API_KEY"] = "test-key"
os.environ["REDUCER_KAFKA_API_SECRET"] = "test-secret"
os.environ["KAFKA_API_SECRET"] = "test-secret"

import pytest
from shared.models import RulesConfig
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.models import Base
import reducer.writer as writer
import shared.rules as retriever


@pytest.fixture
def rules_config() -> RulesConfig:
    return RulesConfig(
        entropy_alpha=0.2,
        max_rate_for_entropy=10.0,
        calm_threshold=0.3,
        hot_threshold=0.6,
        chaos_threshold=0.85,
        cooldown_calm_ms=1000,
        cooldown_warm_ms=2000,
        cooldown_chaos_ms=5000,
        reveal_calm_ms=200,
        reveal_warm_ms=400,
        reveal_chaos_ms=800,
    )


@pytest.fixture
def sqlite_engine(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def patch_writer_db(sqlite_engine, monkeypatch):
    Base.metadata.create_all(sqlite_engine)
    monkeypatch.setattr(writer, "engine", sqlite_engine, raising=True)
    monkeypatch.setattr(
        writer, "SessionLocal", sessionmaker(bind=sqlite_engine), raising=True
    )


@pytest.fixture
def patch_retriever_db(sqlite_engine, monkeypatch):
    Base.metadata.create_all(sqlite_engine)
    monkeypatch.setattr(retriever, "engine", sqlite_engine, raising=True)
    monkeypatch.setattr(
        retriever, "SessionLocal", sessionmaker(bind=sqlite_engine), raising=True
    )
