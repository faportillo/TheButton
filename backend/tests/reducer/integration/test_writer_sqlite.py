import datetime
import reducer.writer as writer
from shared.models import CreateGlobalStateEntity, GlobalState
from sqlalchemy import select


def test_write_state_inserts_row(patch_writer_db):
    new_state = CreateGlobalStateEntity(
        last_applied_offset=42,
        updated_at_ms=123456,
        ruleshash="rh",
        counter=7,
        phase=0,
        entropy=0,
        reveal_until_ms=0,
        cooldown_ms=None,
    )

    persisted = writer.write_state(new_state)
    assert persisted.id is not None
    assert persisted.last_applied_offset == 42
    assert persisted.ruleshash == "rh"
    assert isinstance(persisted.created_at, datetime.datetime)

    # verify row exists
    with writer.SessionLocal() as db:
        rows = (
            db.execute(select(GlobalState).where(GlobalState.id == persisted.id))
            .scalars()
            .all()
        )
        assert len(rows) == 1
