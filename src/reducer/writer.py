from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from shared.models import GlobalState, GlobalStateEntity, CreateGlobalStateEntity, PersistedGlobalState
from reducer.config import settings

database_url = settings.database_url

engine = create_engine(database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


def get_latest_state() -> GlobalStateEntity | None:
    """
    Get the latest global state from the database.

    Returns:
        GlobalStateEntity if a state exists, None otherwise.
    """
    with SessionLocal() as db:
        stmt = select(GlobalState).order_by(GlobalState.id.desc()).limit(1)
        row = db.execute(stmt).scalar_one_or_none()

        if row is None:
            return None

        return GlobalStateEntity(
            id=row.id,
            last_applied_offset=row.last_applied_offset,
            updated_at_ms=row.updated_at_ms,
            ruleshash=row.ruleshash,
            counter=row.counter,
            phase=row.phase,
            entropy=row.entropy,
            reveal_until_ms=row.reveal_until_ms,
            cooldown_ms=row.cooldown_ms,
        )


def get_initial_state(rules_hash: str) -> GlobalStateEntity:
    """
    Create an initial state for when no previous state exists.

    Args:
        rules_hash: Hash of the current ruleset

    Returns:
        A zeroed-out GlobalStateEntity ready for processing.
    """
    return GlobalStateEntity(
        id=0,
        last_applied_offset=-1,
        updated_at_ms=0,
        ruleshash=rules_hash,
        counter=0,
        phase=0,
        entropy=0,
        reveal_until_ms=0,
        cooldown_ms=None,
    )


def write_state(state: CreateGlobalStateEntity) -> PersistedGlobalState:
    with SessionLocal.begin() as db:
        row = GlobalState(
            last_applied_offset=state.last_applied_offset,
            ruleshash=state.ruleshash,
            counter=state.counter,
            phase=state.phase,
            entropy=state.entropy,
            reveal_until_ms=state.reveal_until_ms,
            cooldown_ms=state.cooldown_ms,
            updated_at_ms=state.updated_at_ms,
        )
        db.add(row)
        db.flush()

        return PersistedGlobalState(
            id=row.id,
            last_applied_offset=row.last_applied_offset,
            ruleshash=row.ruleshash,
            created_at=row.created_at,
        )
