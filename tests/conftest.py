import os

os.environ.setdefault("TELEGRAM_TOKEN", "test_token")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lmbatbot.database.models import Base


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(engine)
