"""Isolated database and API fixtures."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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
