from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from shared.models import GlobalState, GlobalStateEntity
from reducer.config import settings

database_url = settings.database_url

engine = create_engine(database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


def _orm_to_entity(orm_obj: GlobalState) -> GlobalStateEntity:
    """Convert a GlobalState ORM object to a GlobalStateEntity dataclass."""
    return GlobalStateEntity(
        id=orm_obj.id,
        last_applied_offset=orm_obj.last_applied_offset,
        updated_at_ms=orm_obj.updated_at_ms,
        ruleshash=orm_obj.ruleshash,
        counter=orm_obj.counter,
        phase=orm_obj.phase,
        entropy=orm_obj.entropy,
        reveal_until_ms=orm_obj.reveal_until_ms,
        cooldown_ms=orm_obj.cooldown_ms,
    )


def get_latest_state() -> GlobalStateEntity:
    with SessionLocal.begin() as db:

        stmt = select(GlobalState).order_by(GlobalState.id.desc()).limit(1)
        selected_state: GlobalState | None = db.execute(stmt).scalars().first()
        if selected_state is None:
            raise LookupError("No global state found")

        return _orm_to_entity(selected_state)


def get_state_by_id(id: int) -> GlobalStateEntity:
    with SessionLocal.begin() as db:
        stmt = (
            select(GlobalState)
            .where(GlobalState.id == id)
            .order_by(GlobalState.id.desc())
            .limit(1)
        )
        selected_state: GlobalState | None = db.execute(stmt).scalars().first()
        if selected_state is None:
            raise LookupError("No global state found")

        return _orm_to_entity(selected_state)
