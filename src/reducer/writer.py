from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.models import GlobalState, CreateGlobalStateEntity, PersistedGlobalState
from reducer.config import settings

database_url = settings.database_url

engine = create_engine(database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


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
