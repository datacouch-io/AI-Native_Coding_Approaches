import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient

from db import reset_db
import main


@pytest.fixture()
def client():
    reset_db()
    return TestClient(main.app)
