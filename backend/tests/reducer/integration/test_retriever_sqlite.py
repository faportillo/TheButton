import pytest
from sqlalchemy import insert, select
from shared.models import Ruleset
import shared.rules as retriever


def test_get_latest_rules_returns_latest_ruleset(patch_retriever_db):
    with retriever.SessionLocal.begin() as db:
        db.execute(
            insert(Ruleset).values(
                version=1,
                hash="h1",
                ruleset={
                    "entropy_alpha": 0.2,
                    "max_rate_for_entropy": 10.0,
                    "calm_threshold": 0.3,
                    "hot_threshold": 0.6,
                    "chaos_threshold": 0.85,
                    "cooldown_calm_ms": 1000,
                    "cooldown_warm_ms": 2000,
                    "cooldown_chaos_ms": 5000,
                    "reveal_calm_ms": 200,
                    "reveal_warm_ms": 400,
                    "reveal_chaos_ms": 800,
                },
            )
        )
        db.execute(
            insert(Ruleset).values(
                version=2,
                hash="h2",
                ruleset={
                    "entropy_alpha": 0.1,
                    "max_rate_for_entropy": 8.0,
                    "calm_threshold": 0.25,
                    "hot_threshold": 0.55,
                    "chaos_threshold": 0.9,
                    "cooldown_calm_ms": 900,
                    "cooldown_warm_ms": 1800,
                    "cooldown_chaos_ms": 4500,
                    "reveal_calm_ms": 150,
                    "reveal_warm_ms": 300,
                    "reveal_chaos_ms": 700,
                },
            )
        )

    rs_entity, rs_cfg = retriever.get_latest_rules()
    assert rs_entity.version == 2
    assert rs_entity.hash == "h2"
    assert rs_cfg.calm_threshold == 0.25
