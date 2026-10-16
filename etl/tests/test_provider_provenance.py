import json

import pytest

from bracc_etl.provider_provenance import merge_provider_record

RUC = '20123456789'
SUNAT = {'ruc': RUC, 'legal_name': 'SUNAT NAME', 'trade_name': 'BRAND',
         'source_url': 'https://example.gob.pe/sunat', 'extraction_date': '2026-09-01'}
OSCE = {'ruc': RUC, 'legal_name': 'OSCE NAME', 'trade_name': '',
        'source_url': 'https://example.gob.pe/osce', 'extraction_date': '2026-10-01'}


def test_merge_is_order_independent_and_preserves_each_observation():
    results = []
    for sequence in [[(SUNAT, 'sunat_ruc'), (OSCE, 'osce_sanctions')],
                     [(OSCE, 'osce_sanctions'), (SUNAT, 'sunat_ruc')]]:
        current = {}
        for row, source in sequence * 2:
            current.update(merge_provider_record(current, row, source))
        results.append(current)
    assert results[0] == results[1]
    assert results[0]['legal_name'] == 'SUNAT NAME' and results[0]['trade_name'] == 'BRAND'
    assert len(results[0]['provider_source_records']) == 2
    assert json.loads(results[0]['provider_field_sources'])['legal_name']['source'] == 'sunat_ruc'


def test_old_or_empty_same_source_values_do_not_erase_newer_evidence():
    current = merge_provider_record({}, SUNAT, 'sunat_ruc')
    older = dict(SUNAT, legal_name='OLD NAME', trade_name='', extraction_date='2026-08-01')
    current.update(merge_provider_record(current, older, 'sunat_ruc'))
    assert current['legal_name'] == 'SUNAT NAME' and current['trade_name'] == 'BRAND'
    assert len(current['provider_source_records']) == 2


def test_preserves_legacy_source_and_does_not_copy_sensitive_or_arbitrary_properties():
    existing = dict(SUNAT, source='sunat_ruc', cpf='private', operator_note='keep')
    result = merge_provider_record(existing, OSCE, 'osce_sanctions')
    assert result['legal_name'] == 'SUNAT NAME'
    assert len(result['provider_source_records']) == 2
    assert 'private' not in str(result) and 'operator_note' not in result


def test_placeholder_does_not_hide_declared_osce_name():
    current = merge_provider_record({}, dict(SUNAT, legal_name=f'RUC {RUC}'), 'sunat_ruc')
    current.update(merge_provider_record(current, OSCE, 'osce_sanctions'))
    assert current['legal_name'] == 'OSCE NAME'
    assert json.loads(current['provider_field_sources'])['legal_name']['source'] == 'osce_sanctions'


@pytest.mark.parametrize('records', ['bad json', '{}', '[{}]',
                                    '[{"ruc":"20999999999","source":"sunat_ruc"}]'])
def test_corrupt_or_cross_ruc_history_is_rejected(records):
    with pytest.raises(ValueError):
        merge_provider_record(
            {'ruc': RUC, 'provider_source_records': [records]}, SUNAT, 'sunat_ruc',
        )


def test_rejects_unsupported_sources():
    with pytest.raises(ValueError):
        merge_provider_record({}, SUNAT, 'unregistered')


def test_osce_provider_observation_keeps_originating_filename():
    from unittest.mock import MagicMock

    from bracc_etl.pipelines.pe_osce_sanctions import PeOsceSanctionsPipeline

    provider, _, _ = PeOsceSanctionsPipeline(MagicMock())._normalize_sanction_row(
        {'ruc': RUC, 'sanction_id': 'TEST'}, 0, source_file='sancionados.csv',
    )
    assert provider['source_dataset'] == 'sancionados.csv'


def test_canonical_name_aliases_and_their_attribution_agree():
    existing = {'ruc': RUC, 'legal_name': 'SUNAT LEGAL', 'name': 'OLD ALIAS', 'source': 'sunat_ruc'}
    result = merge_provider_record(existing, dict(OSCE, name='OSCE NAME'), 'osce_sanctions')
    assert result['name'] == result['legal_name'] == 'SUNAT LEGAL'
    fields = json.loads(result['provider_field_sources'])
    assert fields['name'] == fields['legal_name']


def test_legacy_name_only_is_not_replaced_by_a_placeholder():
    existing = {'ruc': RUC, 'name': 'KNOWN NAME', 'source': 'sunat_ruc'}
    result = merge_provider_record(existing, {'ruc': RUC, 'legal_name': f'RUC {RUC}'}, 'sunat_ruc')
    assert result['legal_name'] == result['name'] == 'KNOWN NAME'
