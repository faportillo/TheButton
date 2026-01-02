import pytest
from sqlalchemy import insert
from shared.models import GlobalState
import api.state as state


class TestGetLatestState:
    """Integration tests for get_latest_state function."""

    def test_returns_latest_state_by_id(self, patch_state_db):
        """Should return the state with the highest id."""
        with state.SessionLocal.begin() as db:
            db.execute(
                insert(GlobalState).values(
                    last_applied_offset=10,
                    updated_at_ms=1000,
                    ruleshash="hash1",
                    counter=5,
                    phase=1,
                    entropy=100,
                    reveal_until_ms=500,
                    cooldown_ms=200,
                )
            )
            db.execute(
                insert(GlobalState).values(
                    last_applied_offset=20,
                    updated_at_ms=2000,
                    ruleshash="hash2",
                    counter=10,
                    phase=2,
                    entropy=200,
                    reveal_until_ms=1000,
                    cooldown_ms=400,
                )
            )

        result = state.get_latest_state()

        assert result["last_applied_offset"] == 20
        assert result["updated_at_ms"] == 2000
        assert result["counter"] == 10
        assert result["phase"] == 2
        assert result["entropy"] == 200
        assert result["reveal_until_ms"] == 1000
        assert result["cooldown_ms"] == 400

    def test_returns_dict(self, patch_state_db):
        """Should return a dictionary."""
        with state.SessionLocal.begin() as db:
            db.execute(
                insert(GlobalState).values(
                    last_applied_offset=1,
                    updated_at_ms=100,
                    ruleshash="test",
                    counter=1,
                    phase=0,
                    entropy=0,
                    reveal_until_ms=0,
                    cooldown_ms=None,
                )
            )

        result = state.get_latest_state()

        assert isinstance(result, dict)

    def test_handles_null_cooldown_ms(self, patch_state_db):
        """Should handle null cooldown_ms correctly."""
        with state.SessionLocal.begin() as db:
            db.execute(
                insert(GlobalState).values(
                    last_applied_offset=1,
                    updated_at_ms=100,
                    ruleshash="test",
                    counter=1,
                    phase=0,
                    entropy=0,
                    reveal_until_ms=0,
                    cooldown_ms=None,
                )
            )

        result = state.get_latest_state()

        assert result["cooldown_ms"] is None

    def test_raises_lookup_error_when_no_state_exists(self, patch_state_db):
        """Should raise LookupError when no state exists in database."""
        with pytest.raises(LookupError, match="No global state found"):
            state.get_latest_state()


class TestGetStateById:
    """Integration tests for get_state_by_id function."""

    def test_returns_state_with_matching_id(self, patch_state_db):
        """Should return the state with the specified id."""
        with state.SessionLocal.begin() as db:
            db.execute(
                insert(GlobalState).values(
                    last_applied_offset=10,
                    updated_at_ms=1000,
                    ruleshash="hash1",
                    counter=5,
                    phase=1,
                    entropy=100,
                    reveal_until_ms=500,
                    cooldown_ms=200,
                )
            )
            db.execute(
                insert(GlobalState).values(
                    last_applied_offset=20,
                    updated_at_ms=2000,
                    ruleshash="hash2",
                    counter=10,
                    phase=2,
                    entropy=200,
                    reveal_until_ms=1000,
                    cooldown_ms=400,
                )
            )

        # Get the first state by id=1
        result = state.get_state_by_id(1)

        assert result["id"] == 1
        assert result["last_applied_offset"] == 10
        assert result["updated_at_ms"] == 1000
        assert result["counter"] == 5
        assert result["phase"] == 1
        assert result["entropy"] == 100
        assert result["reveal_until_ms"] == 500
        assert result["cooldown_ms"] == 200

    def test_returns_second_state_by_id(self, patch_state_db):
        """Should return the second state when requested by id=2."""
        with state.SessionLocal.begin() as db:
            db.execute(
                insert(GlobalState).values(
                    last_applied_offset=10,
                    updated_at_ms=1000,
                    ruleshash="hash1",
                    counter=5,
                    phase=1,
                    entropy=100,
                    reveal_until_ms=500,
                    cooldown_ms=200,
                )
            )
            db.execute(
                insert(GlobalState).values(
                    last_applied_offset=20,
                    updated_at_ms=2000,
                    ruleshash="hash2",
                    counter=10,
                    phase=2,
                    entropy=200,
                    reveal_until_ms=1000,
                    cooldown_ms=400,
                )
            )

        result = state.get_state_by_id(2)

        assert result["id"] == 2
        assert result["last_applied_offset"] == 20

    def test_returns_dict(self, patch_state_db):
        """Should return a dictionary."""
        with state.SessionLocal.begin() as db:
            db.execute(
                insert(GlobalState).values(
                    last_applied_offset=1,
                    updated_at_ms=100,
                    ruleshash="test",
                    counter=1,
                    phase=0,
                    entropy=0,
                    reveal_until_ms=0,
                    cooldown_ms=None,
                )
            )

        result = state.get_state_by_id(1)

        assert isinstance(result, dict)

    def test_raises_lookup_error_when_id_not_found(self, patch_state_db):
        """Should raise LookupError when no state with given id exists."""
        with state.SessionLocal.begin() as db:
            db.execute(
                insert(GlobalState).values(
                    last_applied_offset=1,
                    updated_at_ms=100,
                    ruleshash="test",
                    counter=1,
                    phase=0,
                    entropy=0,
                    reveal_until_ms=0,
                    cooldown_ms=None,
                )
            )

        with pytest.raises(LookupError, match="No global state found"):
            state.get_state_by_id(999)

    def test_raises_lookup_error_when_no_state_exists(self, patch_state_db):
        """Should raise LookupError when no state exists in database."""
        with pytest.raises(LookupError, match="No global state found"):
            state.get_state_by_id(1)


class TestOrmToDict:
    """Unit tests for _orm_to_dict helper function."""

    def test_converts_all_fields_correctly(self, patch_state_db):
        """Should correctly map all ORM fields to dictionary fields."""
        with state.SessionLocal.begin() as db:
            db.execute(
                insert(GlobalState).values(
                    last_applied_offset=42,
                    updated_at_ms=123456,
                    ruleshash="testhash",
                    counter=7,
                    phase=3,
                    entropy=500,
                    reveal_until_ms=1500,
                    cooldown_ms=750,
                )
            )

        with state.SessionLocal() as db:
            from sqlalchemy import select

            orm_obj = db.execute(select(GlobalState)).scalars().first()
            result = state._orm_to_dict(orm_obj)

        assert result["id"] == 1
        assert result["last_applied_offset"] == 42
        assert result["updated_at_ms"] == 123456
        assert result["counter"] == 7
        assert result["phase"] == 3
        assert result["entropy"] == 500
        assert result["reveal_until_ms"] == 1500
        assert result["cooldown_ms"] == 750
        assert "created_at" in result
        assert result["created_at"] is not None

    def test_result_is_dict(self, patch_state_db):
        """Should return a dictionary."""
        with state.SessionLocal.begin() as db:
            db.execute(
                insert(GlobalState).values(
                    last_applied_offset=1,
                    updated_at_ms=100,
                    ruleshash="test",
                    counter=1,
                    phase=0,
                    entropy=0,
                    reveal_until_ms=0,
                    cooldown_ms=None,
                )
            )

        with state.SessionLocal() as db:
            from sqlalchemy import select

            orm_obj = db.execute(select(GlobalState)).scalars().first()
            result = state._orm_to_dict(orm_obj)

        assert isinstance(result, dict)
        # Dictionary can be modified
        result["counter"] = 999
        assert result["counter"] == 999

