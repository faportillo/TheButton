from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import DateTime, JSON, BigInteger, Float
from sqlalchemy.sql import func
import datetime
from dataclasses import dataclass
from typing import Optional

# ==================================================
# DOMAIN ENTITIES
# ==================================================


@dataclass(frozen=True)
class CreateGlobalStateEntity:
    last_applied_offset: int
    updated_at_ms: int
    ruleshash: str
    counter: int
    phase: int
    entropy: int
    reveal_until_ms: int
    cooldown_ms: Optional[int]


@dataclass(frozen=True)
class GlobalStateEntity(CreateGlobalStateEntity):
    id: int


@dataclass(frozen=True)
class PersistedGlobalState:
    id: int
    last_applied_offset: int
    ruleshash: str
    created_at: datetime.datetime


@dataclass(frozen=True)
class CreateRulesetEntity:
    version: int
    hash: int
    ruleset: str


@dataclass(frozen=True)
class RulesConfig:
    entropy_alpha: float
    max_rate_for_entropy: float  # presses/sec

    calm_threshold: float
    hot_threshold: float
    chaos_threshold: float

    cooldown_calm_ms: int
    cooldown_warm_ms: int
    cooldown_chaos_ms: int

    reveal_calm_ms: int
    reveal_warm_ms: int
    reveal_chaos_ms: int


@dataclass(frozen=True)
class RulesetEntity(CreateRulesetEntity):
    id: int


@dataclass(frozen=True)
class PressEvent:
    offset: int
    timestamp_ms: int
    request_id: str


# ==================================================
#  SQLAlchemy ORM Table Models
# ==================================================


class Base(DeclarativeBase):
    pass


class GlobalState(Base):
    __tablename__ = "global_states"

    # The 'id' column automatically becomes an auto-incrementing counter
    # because it is an Integer and set as the primary key.
    id: Mapped[int] = mapped_column(primary_key=True)
    last_applied_offset: Mapped[int] = mapped_column(nullable=False)
    ruleshash: Mapped[str] = mapped_column(nullable=False)
    counter: Mapped[int] = mapped_column(nullable=False)
    phase: Mapped[int] = mapped_column(nullable=False)
    entropy: Mapped[float] = mapped_column(Float, nullable=False)
    reveal_until_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cooldown_ms: Mapped[int] = mapped_column(nullable=True)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Ruleset(Base):
    __tablename__ = "rulesets"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(nullable=False)
    hash: Mapped[str] = mapped_column(nullable=False)
    # Use generic JSON for cross-dialect support, with JSONB on PostgreSQL
    ruleset: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
