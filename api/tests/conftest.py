from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bracc.main import app
from bracc.routers import baseline, emendas, investigation
from bracc.services.auth_service import create_access_token


@pytest.fixture
def mock_driver() -> MagicMock:
    # Mock Neo4j driver so tests don't need a running database
    mock_driver = MagicMock()
    mock_driver.verify_connectivity = AsyncMock()
    mock_driver.close = AsyncMock()
    mock_session = AsyncMock()
    mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=None)
    app.state.neo4j_driver = mock_driver

    return mock_driver


@pytest.fixture
async def client(mock_driver: MagicMock) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def legacy_client(mock_driver: MagicMock) -> AsyncIterator[AsyncClient]:
    """Exercise retained upstream routers without registering them in PE-ACC."""
    isolated_app = FastAPI(
        middleware=app.user_middleware,
        exception_handlers=app.exception_handlers,
        redirect_slashes=False,
    )
    isolated_app.state.neo4j_driver = mock_driver
    isolated_app.state.limiter = app.state.limiter
    isolated_app.include_router(baseline.router)
    isolated_app.include_router(emendas.router)
    isolated_app.include_router(investigation.router)
    isolated_app.include_router(investigation.shared_router)
    transport = ASGITransport(app=isolated_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers() -> dict[str, str]:
    token = create_access_token("test-user-id")
    return {"Authorization": f"Bearer {token}"}
