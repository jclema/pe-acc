import json

import pandas as pd
import pytest

from bracc_etl.pipelines.pe_osce_sanctions import PeOsceSanctionsPipeline
from bracc_etl.pipelines.pe_sunat_ruc import PeSunatRucPipeline


@pytest.mark.integration
@pytest.mark.parametrize('reverse,streaming', [(False, False), (True, False),
                                              (False, True), (True, True)])
def test_provider_sources_survive_order_and_repeated_load(
    neo4j_driver, tmp_path, reverse, streaming,
):
    ruc = f'2099000000{1 + int(reverse) + 2 * int(streaming)}'
    sunat = PeSunatRucPipeline(neo4j_driver, data_dir=str(tmp_path), chunk_size=1)
    row = {'ruc': ruc, 'legal_name': 'Identidad SUNAT', 'trade_name': 'Marca SUNAT',
           'tax_status': 'ACTIVO', 'source_url': 'https://example.gob.pe/sunat',
           'extraction_date': '2026-09-01', 'source_dataset': 'sunat.csv'}
    if streaming:
        raw = tmp_path / 'raw/pe/sunat_ruc'
        raw.mkdir(parents=True)
        pd.DataFrame([row]).to_csv(raw / 'sunat.csv', index=False)
        sunat.extract()
    else:
        sunat._raw_providers = pd.DataFrame([row])
    sunat.transform()
    osce = PeOsceSanctionsPipeline(neo4j_driver, data_dir=str(tmp_path))
    osce._raw_sanctions = pd.DataFrame([{
        'ruc': ruc, 'provider_name': 'Nombre declarado OSCE', 'sanction_id': 'TEST-001',
        'source_url': 'https://example.gob.pe/osce', 'extraction_date': '2026-10-01',
    }])
    osce.transform()
    ordered = [osce, sunat] if reverse else [sunat, osce]
    previous = None
    for _ in range(2):
        for pipeline in ordered:
            pipeline.load()
        with neo4j_driver.session() as session:
            props = session.run('MATCH (p:Provider {ruc:$ruc}) RETURN properties(p) AS p',
                                ruc=ruc).single()['p']
            links = session.run(
                'MATCH (p:Provider {ruc:$ruc})-[:HAS_SANCTION]->(s:Sanction) '
                'RETURN s.ruc AS ruc, s.source_url AS url', ruc=ruc,
            ).data()
        assert props['legal_name'] == 'IDENTIDAD SUNAT'
        assert props['trade_name'] == 'MARCA SUNAT' and props['tax_status'] == 'ACTIVO'
        assert props['source'] == 'sunat_ruc'
        assert props['sources'] == ['osce_sanctions', 'sunat_ruc']
        records = [json.loads(value) for value in props['provider_source_records']]
        assert {r['source'] for r in records} == {'sunat_ruc', 'osce_sanctions'}
        assert any(r['legal_name'] == 'NOMBRE DECLARADO OSCE' for r in records)
        fields = json.loads(props['provider_field_sources'])
        assert fields['legal_name']['source'] == 'sunat_ruc'
        assert fields['legal_name']['extraction_date'] == '2026-09-01'
        assert links == [{'ruc': ruc, 'url': 'https://example.gob.pe/osce'}]
        if previous is not None:
            assert props == previous
        previous = props


@pytest.mark.integration
def test_corrupt_history_rolls_back_whole_provider_batch(neo4j_driver):
    from bracc_etl.loader import Neo4jBatchLoader

    with neo4j_driver.session() as session:
        session.run("CREATE (:Provider {ruc:'20990000005', legal_name:'LEGACY', "
                    "operator_note:'keep', provider_source_records:['bad json']})").consume()
    loader = Neo4jBatchLoader(neo4j_driver)
    with pytest.raises(ValueError):
        loader.load_provider_records([{'ruc': '20990000006', 'legal_name': 'NEW'},
                                      {'ruc': '20990000005', 'legal_name': 'UPDATE'}], 'sunat_ruc')
    with neo4j_driver.session() as session:
        rows = session.run("MATCH (p:Provider) WHERE p.ruc IN ['20990000005','20990000006'] "
                           'RETURN p.legal_name AS name, p.operator_note AS note').data()
    assert rows == [{'name': 'LEGACY', 'note': 'keep'}]


@pytest.mark.integration
def test_concurrent_provider_updates_keep_all_source_evidence(neo4j_driver):
    from concurrent.futures import ThreadPoolExecutor

    from bracc_etl.loader import Neo4jBatchLoader

    with neo4j_driver.session() as session:
        session.run("CREATE CONSTRAINT provider_ruc_unique IF NOT EXISTS "
                    "FOR (p:Provider) REQUIRE p.ruc IS UNIQUE").consume()
    loader = Neo4jBatchLoader(neo4j_driver)
    def load(index):
        return loader.load_provider_records([
            {'ruc': '20990000007', 'legal_name': f'SUNAT {index}',
             'extraction_date': f'2026-09-{index + 1:02d}'},
        ], 'sunat_ruc' if index % 2 else 'osce_sanctions')
    with ThreadPoolExecutor(max_workers=4) as executor:
        assert list(executor.map(load, range(8))) == [1] * 8
    with neo4j_driver.session() as session:
        props = session.run("MATCH (p:Provider {ruc:'20990000007'}) RETURN properties(p) AS p"
                            ).single()['p']
    assert len(props['provider_source_records']) == 8
    assert props['legal_name'] == 'SUNAT 7'
    assert props['sources'] == ['osce_sanctions', 'sunat_ruc']
