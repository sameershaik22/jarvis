from __future__ import annotations

import os
from pathlib import Path
import tempfile

# Force test environment and local SQLite database BEFORE any app imports
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.gettempdir()).resolve().as_posix()}/test_yoursbuddy.sqlite3"
os.environ["BROWSER_HEADLESS"] = "true"

import httpx
import pytest
import pytest_asyncio

from app.config import get_settings
from app.db.session import init_db, reconfigure_engine


@pytest.fixture(scope="session")
def test_workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("yb_test")
    (root / "data" / "screenshots").mkdir(parents=True, exist_ok=True)
    (root / "data" / "browser_profile").mkdir(parents=True, exist_ok=True)
    (root / "exports").mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture(scope="session")
def test_app(test_workspace: Path):
    db_file = test_workspace / "test_yoursbuddy.sqlite3"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_file.as_posix()}"
    os.environ["BROWSER_HEADLESS"] = "true"
    os.environ["BROWSER_USER_DATA_DIR"] = str(test_workspace / "data" / "browser_profile")

    get_settings.cache_clear()
    settings = get_settings()
    settings.data_dir = test_workspace / "data"
    settings.screenshots_dir = test_workspace / "data" / "screenshots"
    settings.exports_dir = test_workspace / "exports"
    settings.ensure_directories()

    eng = reconfigure_engine(os.environ["DATABASE_URL"])
    init_db(eng)

    from app.main import create_app

    return create_app()


@pytest_asyncio.fixture
async def async_client(test_app):
    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
