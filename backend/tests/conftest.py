"""Isolated database and API fixtures."""

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Tests must stay deterministic and offline even when a developer's local .env is
# configured for a real provider. Individual tests can still override these values
# explicitly through Settings constructor arguments.
os.environ["MOCK_LLM"] = "true"
os.environ["MOCK_EXTERNAL_APIS"] = "true"
os.environ["DEMO_MODE"] = "false"
os.environ["LLM_BASE_URL"] = ""
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_MODEL"] = ""
os.environ["LLM_MIN_REQUEST_INTERVAL_SECONDS"] = "0"

from app.db.base import Base
from app.db.session import (
    create_database_engine,
    create_session_factory,
    get_db,
    init_db,
)
from app.main import create_app


@pytest.fixture
def session() -> Generator[Session, None, None]:
    database_engine = create_database_engine("sqlite+pysqlite://", in_memory=True)
    init_db(database_engine)
    factory = create_session_factory(database_engine)

    with factory() as database_session:
        yield database_session

    Base.metadata.drop_all(database_engine)
    database_engine.dispose()


@pytest.fixture
def client(session: Session) -> Generator[TestClient, None, None]:
    application = create_app(initialize_database=False)

    def override_database() -> Generator[Session, None, None]:
        yield session

    application.dependency_overrides[get_db] = override_database
    with TestClient(application) as test_client:
        yield test_client
    application.dependency_overrides.clear()
