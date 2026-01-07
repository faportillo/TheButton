"""
Shared rules retriever - provides access to rulesets for all services.

This module allows reducer, watcher, and other services to retrieve rules
consistently without creating cross-dependencies.
"""
import os
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from shared.models import Ruleset, RulesConfig, RulesetEntity
from typing import Tuple

# Get database URL from environment (all services have DATABASE_URL)
database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise ValueError("DATABASE_URL environment variable is required")

engine = create_engine(database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


def get_latest_rules() -> Tuple[RulesetEntity, RulesConfig]:
    """Get the latest ruleset from the database."""
    with SessionLocal.begin() as db:
        stmt = select(Ruleset).order_by(Ruleset.id.desc()).limit(1)
        selected_rules: Ruleset | None = db.execute(stmt).scalars().first()
        if selected_rules is None:
            raise LookupError("No ruleset found")

        rules_config = RulesConfig(**selected_rules.ruleset)
        rules_entity = RulesetEntity(
            id=selected_rules.id,
            version=selected_rules.version,
            hash=selected_rules.hash,
            ruleset=selected_rules.ruleset,
        )
        return rules_entity, rules_config


def get_rules_by_hash(rules_hash: str) -> Tuple[RulesetEntity, RulesConfig]:
    """Get rules by hash to ensure consistency with state.
    
    This ensures that services use the exact rules version that was used
    to compute a given state, preventing inconsistencies when rules are updated.
    
    Args:
        rules_hash: The hash of the ruleset to retrieve
        
    Returns:
        Tuple of (RulesetEntity, RulesConfig)
        
    Raises:
        LookupError: If no ruleset with the given hash is found
    """
    with SessionLocal.begin() as db:
        stmt = select(Ruleset).where(Ruleset.hash == rules_hash).limit(1)
        selected_rules: Ruleset | None = db.execute(stmt).scalars().first()
        if selected_rules is None:
            raise LookupError(f"No ruleset found with hash: {rules_hash}")

        rules_config = RulesConfig(**selected_rules.ruleset)
        rules_entity = RulesetEntity(
            id=selected_rules.id,
            version=selected_rules.version,
            hash=selected_rules.hash,
            ruleset=selected_rules.ruleset,
        )
        return rules_entity, rules_config


def get_rules_version(version: int) -> RulesetEntity:
    """Get rules by version number.
    
    Note: This is not yet implemented.
    """
    raise NotImplementedError()

