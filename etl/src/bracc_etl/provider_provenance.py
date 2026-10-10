"""Preserve source observations while projecting a stable Peru Provider identity."""
from __future__ import annotations

import json
from datetime import date
from typing import Any

FIELDS = ('legal_name', 'name', 'trade_name', 'tax_status', 'tax_condition', 'provider_type',
          'ubigeo', 'department', 'province', 'district')
META = ('source', 'source_url', 'source_dataset', 'extraction_date')
PRIORITY = {'sunat_ruc': 2, 'osce_sanctions': 1}


def merge_provider_record(
    existing: dict[str, Any], row: dict[str, Any], source: str,
) -> dict[str, Any]:
    if source not in PRIORITY:
        raise ValueError('Unsupported Provider source')
    ruc = str(row.get('ruc', ''))
    if len(ruc) != 11 or not ruc.isascii() or not ruc.isdigit():
        raise ValueError('Provider evidence requires an eleven-digit RUC')
    history = existing.get('provider_source_records', [])
    if not isinstance(history, list):
        raise ValueError('Invalid Provider source history')
    observations = []
    for encoded in history:
        try:
            record = json.loads(encoded)
        except (ValueError, TypeError) as exc:
            raise ValueError('Invalid Provider source history') from exc
        if (not isinstance(record, dict) or record.get('ruc') != ruc
                or not record.get('source') or set(record) - {*FIELDS, *META, 'ruc'}
                or any(not isinstance(value, str) for value in record.values())):
            raise ValueError('Invalid or cross-RUC Provider source history')
        observations.append(record)
    if not history and any(existing.get(key) for key in (*FIELDS, *META)):
        observations.append({
            key: str(existing[key]) for key in (*FIELDS, *META) if existing.get(key)
        } | {'ruc': ruc, 'source': str(existing.get('source') or 'legacy_unknown')})
    observations.append({key: str(row[key]) for key in (*FIELDS, *META) if row.get(key)}
                        | {'ruc': ruc, 'source': source})
    encoded_records = sorted({json.dumps(record, sort_keys=True, ensure_ascii=False,
                                         separators=(',', ':')) for record in observations})
    observations = [json.loads(value) for value in encoded_records]

    def rank(record: dict[str, str]) -> tuple[int, str, str]:
        try:
            cutoff = date.fromisoformat(record.get('extraction_date', '')).isoformat()
        except ValueError:
            cutoff = ''
        return PRIORITY.get(record['source'], 0), cutoff, json.dumps(record, sort_keys=True)

    observations.sort(key=rank)
    selected = {}
    result: dict[str, Any] = {'ruc': ruc}
    for record in observations:
        for field in FIELDS:
            value = record.get(field)
            if value and not (field in {'name', 'legal_name'} and value == f'RUC {ruc}'):
                result[field] = value
                selected[field] = {key: record.get(key, '') for key in META}
    primary = selected.get('legal_name') or selected.get('name') or observations[-1]
    result.update({key: primary.get(key, '') for key in META})
    result['legal_name'] = result['name'] = (
        result.get('legal_name') or result.get('name') or f'RUC {ruc}'
    )
    identity = selected.get('legal_name') or selected.get('name')
    if identity:
        selected['legal_name'] = selected['name'] = identity
    result['sources'] = sorted({record['source'] for record in observations})
    result['provider_source_records'] = encoded_records
    result['provider_field_sources'] = json.dumps(selected, sort_keys=True, ensure_ascii=False)
    return result
