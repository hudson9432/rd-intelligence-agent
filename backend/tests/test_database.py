"""Database initialization and file-backed persistence tests."""

from pathlib import Path

from app.db.session import create_database_engine, create_session_factory, init_db
from app.repositories import ResearchMissionRepository
from app.schemas import ResearchMissionCreate


def test_file_database_persists_across_sessions(tmp_path: Path) -> None:
    database_path = tmp_path / "persistence.db"
    database_engine = create_database_engine(f"sqlite:///{database_path}")
    init_db(database_engine)
    factory = create_session_factory(database_engine)

    with factory() as first_session:
        mission = ResearchMissionRepository(first_session).create(
            ResearchMissionCreate(title="Persistent mission", goal="Survive reconnect")
        )
        mission_id = mission.id

    with factory() as second_session:
        restored = ResearchMissionRepository(second_session).get(mission_id)
        assert restored is not None
        assert restored.title == "Persistent mission"

    database_engine.dispose()
