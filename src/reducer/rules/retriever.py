from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from shared.models import Ruleset, RulesConfig, RulesetEntity
from reducer.config import settings
from typing import Tuple

database_url = settings.database_url

engine = create_engine(database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


def get_latest_rules() -> Tuple[RulesetEntity, RulesConfig]:
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


def get_rules_version(version: int) -> RulesetEntity:
    raise NotImplementedError()
