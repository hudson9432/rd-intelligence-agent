"""Database initialization and file-backed persistence tests."""

from pathlib import Path

from sqlalchemy import inspect, text

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


def test_init_db_migrates_legacy_business_impact_column(tmp_path: Path) -> None:
    """A database created before goal_alignment must survive an application update."""

    database_engine = create_database_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    init_db(database_engine)
    with database_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO research_missions "
                "(id, title, goal, status, created_at, updated_at) VALUES "
                "('mission-1', 'Legacy mission', 'goal', 'created', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE technology_opportunities "
                "RENAME COLUMN goal_alignment TO business_impact"
            )
        )
        connection.execute(
            text(
                "INSERT INTO technology_opportunities "
                "(id, mission_id, name, description, related_evidence_ids_json, "
                "novelty, technical_maturity, implementation_difficulty, "
                "business_impact, poc_feasibility, evidence_strength, overall_score, "
                "rationale, created_at) VALUES "
                "('opportunity-1', 'mission-1', 'Legacy candidate', 'description', "
                "'[]', 3, 3, 3, 4, 3, 3, 50, 'rationale', CURRENT_TIMESTAMP)"
            )
        )

    init_db(database_engine)

    columns = {
        column["name"]
        for column in inspect(database_engine).get_columns("technology_opportunities")
    }
    assert "goal_alignment" in columns
    assert "business_impact" not in columns
    with database_engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT goal_alignment FROM technology_opportunities WHERE id='opportunity-1'"
                )
            )
            == 4
        )
    database_engine.dispose()
