import json
from unittest.mock import AsyncMock, patch

import pytest

from bracc.config import settings
from bracc.routers.entity import _node_to_entity
from bracc.services.neo4j_service import sanitize_props

RUC = '20123456789'


def provider(**extra):
    return {'ruc': RUC, 'legal_name': 'DEMO', 'tax_status': 'ACTIVO',
            'source': 'sunat_ruc', **extra}


def test_selected_fields_use_their_own_metadata_without_exposing_history():
    props = provider(sources=['sunat_ruc', 'osce_sanctions'], provider_field_sources=json.dumps({
        'legal_name': {'source': 'sunat_ruc', 'source_url': 'https://www.sunat.gob.pe/',
                       'source_dataset': '/internal/raw/padron.csv',
                       'extraction_date': '2026-09-01', 'cpf': 'PRIVATE'},
        'tax_status': {'source': 'osce_sanctions'}, 'cpf': {'source': 'PRIVATE'},
    }), provider_source_records=['PRIVATE'])
    result = _node_to_entity(props, ['Provider'], RUC).model_dump()
    evidence = result['provider_provenance']
    assert evidence['status'] == 'structured'
    assert set(evidence['fields']) == {'legal_name', 'tax_status'}
    assert evidence['fields']['legal_name'] == {
        'source': 'sunat_ruc', 'source_url': 'https://www.sunat.gob.pe/',
        'source_dataset': 'padron.csv', 'extraction_date': '2026-09-01',
    }
    assert evidence['fields']['tax_status']['source'] == 'osce_sanctions'
    assert evidence['fields']['tax_status']['extraction_date'] is None
    assert [s['database'] for s in result['sources']] == ['sunat_ruc', 'osce_sanctions']
    assert 'PRIVATE' not in json.dumps(result)


@pytest.mark.parametrize('raw', ['{', '[]', 'null', '1', {}, ['wrong']])
def test_invalid_json_is_unknown_without_using_scalar_source(raw):
    result = _node_to_entity(provider(provider_field_sources=raw), ['Provider'], RUC)
    evidence = result.model_dump()['provider_provenance']
    assert evidence['status'] == 'invalid'
    assert all(item['source'] is None for item in evidence['fields'].values())


def test_legacy_sources_do_not_claim_field_attribution_or_reconstruct_history():
    result = _node_to_entity(provider(source_dataset='demo.csv'), ['Provider'], RUC).model_dump()
    assert result['provider_provenance']['status'] == 'legacy'
    assert result['provider_provenance']['fields']['legal_name']['source'] is None
    assert result['sources'][0]['database'] == 'sunat_ruc'
    assert _node_to_entity({'ruc': RUC}, ['Provider'], RUC).model_dump()[
        'provider_provenance']['fields'] == {}
    assert _node_to_entity({'name': 'Company'}, ['Company'], 'id').model_dump()[
        'provider_provenance'] is None


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'https://sunat.gob.pe.evil.com/',
                                 'https://user:pass@sunat.gob.pe/', 'http://sunat.gob.pe/',
                                 'https://sunat.gob.pe:444/', 'https://evil.com/',
                                 'https://sunat.gob.pe/\nsecret'])
def test_untrusted_links_and_invalid_metadata_are_not_published(url):
    props = provider(provider_field_sources=json.dumps({'legal_name': {
        'source': 'sunat_ruc', 'source_url': url, 'extraction_date': 'downloaded yesterday',
        'source_dataset': 42}, 'tax_status': {'source': ['private']}}))
    fields = _node_to_entity(props, ['Provider'], RUC).model_dump()['provider_provenance']['fields']
    assert fields['legal_name']['source_url'] is None
    assert fields['legal_name']['extraction_date'] is None
    assert fields['legal_name']['source_dataset'] is None
    assert fields['tax_status']['source'] is None


@pytest.mark.parametrize('public_mode', [True, False])
def test_internal_provenance_is_never_flattened_into_generic_properties(public_mode, monkeypatch):
    monkeypatch.setattr(settings, 'public_mode', public_mode)
    assert sanitize_props({'name': 'DEMO', 'provider_source_records': ['PRIVATE'],
                           'provider_field_sources': 'PRIVATE'}) == {'name': 'DEMO'}


@pytest.mark.parametrize('path', [f'/api/v1/entity/{RUC}', '/api/v1/entity/by-element-id/p:1'])
async def test_existing_lookup_responses_have_typed_provenance(client, path):
    record = {'e': provider(), 'entity_labels': ['Provider'], 'entity_id': RUC}
    with patch('bracc.routers.entity.execute_query_single', AsyncMock(return_value=record)):
        response = await client.get(path)
    assert response.status_code == 200
    assert response.json()['provider_provenance']['status'] == 'legacy'


async def test_connections_project_provider_fields_and_hide_internal_history(client):
    record = {'e': provider(), 'source_labels': ['Provider'], 'source_id': RUC,
              'connected': provider(provider_source_records=['PRIVATE']),
              'target_labels': ['Provider'], 'target_id': '20111111111',
              'r': {}, 'rel_type': 'RELATED_TO'}
    with patch('bracc.routers.entity.execute_query', AsyncMock(return_value=[record])):
        response = await client.get(f'/api/v1/entity/{RUC}/connections')
    assert response.status_code == 200
    assert response.json()['entity']['provider_provenance']['status'] == 'legacy'
    assert response.json()['connected_entities'][0]['provider_provenance']['status'] == 'legacy'
    assert 'PRIVATE' not in response.text


@pytest.mark.parametrize('source', ['legacy_unknown', 'private_source', 'seace_conosce', None, 42])
def test_unknown_field_sources_cannot_publish_metadata(source):
    props = provider(provider_field_sources=json.dumps({'legal_name': {
        'source': source, 'source_url': 'https://sunat.gob.pe/', 'source_dataset': 'SECRET'}}))
    field = _node_to_entity(props, ['Provider'], RUC).model_dump()[
        'provider_provenance']['fields']['legal_name']
    assert all(value is None for value in field.values())


async def test_public_lookup_boundary_remains_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, 'public_mode', True)
    monkeypatch.setattr(settings, 'public_allow_entity_lookup', False)
    response = await client.get(f'/api/v1/entity/{RUC}')
    assert response.status_code == 403
