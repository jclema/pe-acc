import pytest
from httpx import AsyncClient

from bracc.routers.graph import _slim_props


def test_slim_props_keeps_sanction_traceability_fields() -> None:
    source_url = "https://www.datosabiertos.gob.pe/dataset/proveedores-sancionados"

    properties = _slim_props(
        {
            "sanction_id": "OSCE-001",
            "sanction_source": "OSCE_TCP",
            "resolution_number": "001-2026-TCE",
            "reason": "Registro publicado por la fuente",
            "date_start": "2026-01-01",
            "date_end": "2026-12-31",
            "source_url": source_url,
            "internal_only": "must not be exposed",
        }
    )

    assert properties == {
        "sanction_id": "OSCE-001",
        "sanction_source": "OSCE_TCP",
        "resolution_number": "001-2026-TCE",
        "reason": "Registro publicado por la fuente",
        "date_start": "2026-01-01",
        "date_end": "2026-12-31",
        "source_url": source_url,
    }


@pytest.mark.anyio
async def test_graph_rejects_invalid_depth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/graph/test-id?depth=5")
    assert response.status_code == 422


@pytest.mark.anyio
async def test_graph_accepts_valid_depth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/graph/test-id?depth=2")
    assert response.status_code != 422


@pytest.mark.anyio
async def test_graph_accepts_entity_types_filter(client: AsyncClient) -> None:
    response = await client.get("/api/v1/graph/test-id?entity_types=person,company")
    assert response.status_code != 422
