import json

import pytest
from httpx import AsyncClient
from neo4j import AsyncSession

from bracc.config import settings


@pytest.mark.integration
@pytest.mark.anyio
async def test_entity_lookup_by_cpf(integration_client: AsyncClient) -> None:
    """Lookup a seeded Person entity by CPF."""
    response = await integration_client.get("/api/v1/entity/11111111111")
    assert response.status_code in (200, 404)


@pytest.mark.integration
@pytest.mark.anyio
async def test_entity_lookup_by_cnpj(integration_client: AsyncClient) -> None:
    """Lookup a seeded Company entity by CNPJ."""
    response = await integration_client.get("/api/v1/entity/11222333000181")
    assert response.status_code in (200, 404)


@pytest.mark.integration
@pytest.mark.anyio
async def test_entity_not_found(integration_client: AsyncClient) -> None:
    """Lookup a non-existent entity returns 404."""
    response = await integration_client.get("/api/v1/entity/00000000000")
    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.anyio
async def test_entity_invalid_format(integration_client: AsyncClient) -> None:
    """Invalid identifier format returns 400."""
    response = await integration_client.get("/api/v1/entity/abc")
    assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.anyio
async def test_entity_connections(integration_client: AsyncClient) -> None:
    """Lookup connections for an entity."""
    response = await integration_client.get("/api/v1/entity/test-entity-id/connections")
    assert response.status_code in (200, 404)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_provider_connections_return_selected_provenance(
    integration_client: AsyncClient, integration_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = {"legal_name": {
        "source": "osce_sanctions", "source_dataset": "sancionados.csv",
        "source_url": "https://osce-gob-pe.atlassian.net/wiki/pages/viewpage.action?pageId=106889269",
        "extraction_date": "2026-08-08",
    }}
    result = await integration_session.run(
        "CREATE (p:Provider {ruc:'20990000999', legal_name:'PROVEEDOR DE PRUEBA', "
        "source:'osce_sanctions', sources:['osce_sanctions'], "
        "provider_field_sources:$meta, provider_source_records:['internal history']}) "
        "CREATE (s:Sanction {sanction_id:'PROVENANCE-TEST', source:'osce_sanctions'}) "
        "CREATE (p)-[:HAS_SANCTION {source:'osce_sanctions', confidence:1.0}]->(s) "
        "CREATE (u:User {email:'private@example.org'}) "
        "CREATE (p)-[:HAS_SANCTION]->(u) RETURN elementId(p) AS id",
        meta=json.dumps(metadata),
    )
    record = await result.single()
    assert record is not None
    path = f"/api/v1/entity/{record['id']}/connections?depth=1"
    response = await integration_client.get(path)
    assert response.status_code == 200
    body = response.json()
    assert body['entity']['id'] == record['id']
    assert body['entity']['provider_provenance'] == {"status": "structured", "fields": metadata}
    assert len(body['connections']) == len(body['connected_entities']) == 1
    assert body['connections'][0]['relationship_type'] == 'HAS_SANCTION'
    assert body['connected_entities'][0]['properties']['sanction_id'] == 'PROVENANCE-TEST'
    assert 'provider_source_records' not in response.text
    assert 'provider_field_sources' not in response.text
    assert 'private@example.org' not in response.text
    monkeypatch.setattr(settings, 'public_mode', True)
    monkeypatch.setattr(settings, 'public_allow_entity_lookup', False)
    assert (await integration_client.get(path)).status_code == 403
