import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure project root is in sys.path for test execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    """
    Reusable FastAPI TestClient.
    """
    with TestClient(app) as test_client:
        yield test_client
