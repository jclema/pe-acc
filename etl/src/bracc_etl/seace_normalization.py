"""Map verified annual awards to the existing graph, with a corporate-only scope."""
from __future__ import annotations

import json
import math
import re
import zipfile
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

import pandas as pd
from defusedxml.ElementTree import iterparse  # type: ignore[import-untyped]

from bracc_etl.seace_acquisition import COLUMNS, NS, valid_snapshot
from bracc_etl.transforms import normalize_name, parse_date

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _rows(path: Path) -> Iterator[tuple[int, dict[str, str]]]:
    with zipfile.ZipFile(path) as archive:
        strings = []
        with archive.open("xl/sharedStrings.xml") as stream:
            for _, element in iterparse(stream, events=("end",)):
                if element.tag == f"{NS}si":
                    strings.append("".join(t.text or "" for t in element.iter(f"{NS}t")))
                    element.clear()
        with archive.open("xl/worksheets/sheet1.xml") as stream:
            for _, element in iterparse(stream, events=("end",)):
                if element.tag != f"{NS}row":
                    continue
                number = int(element.attrib["r"])
                if number > 1:
                    values = {}
                    for cell in element:
                        address = re.fullmatch(r"([A-Y])[0-9]+", cell.attrib["r"])
                        if address is None or address[1] in values:
                            raise ValueError("Unexpected or duplicate SEACE cell address")
                        value = cell.findtext(f"{NS}v", "")
                        values[address[1]] = strings[int(value)] if cell.get("t") == "s" else value
                    yield number, {key: values.get(chr(65+i), "") for i, key in enumerate(COLUMNS)}
                element.clear()


def normalize_awards(snapshot: Path) -> pd.DataFrame:
    if not valid_snapshot(snapshot):
        raise ValueError("Official SEACE input requires an intact acquisition snapshot")
    meta = json.loads((snapshot / "manifest.json").read_text())
    filename = f"CONOSCE_ADJUDICACIONES{meta['year']}_0.xlsx"
    groups: dict[tuple[str, str], list[tuple[int, dict[str, str]]]] = defaultdict(list)
    count = 0
    for number, row in _rows(snapshot / filename):
        count += 1
        key = row["CODIGOCONVOCATORIA"].strip(), row["N_ITEM"].strip()
        if not all(re.fullmatch(r"[0-9]+", value) for value in key):
            raise ValueError(f"Invalid SEACE process/item key at row {number}")
        groups[key].append((number, row))
    records = []
    for (process, item), group in groups.items():
        # Item totals cannot be assigned to each winner in a prorrata award.
        if len({row["RUC PROVEEDOR"].strip() for _, row in group}) != 1:
            continue
        number, row = group[0]
        ruc = row["RUC PROVEEDOR"].strip()
        if (normalize_name(row["TIPO_PROVEEDOR"]) != "PERSONA JURIDICA"
                or not re.fullmatch(r"20[0-9]{9}", ruc)):
            continue
        if len({tuple(sorted(r.items())) for _, r in group}) != 1:
            raise ValueError(f"Conflicting SEACE observations for {process}/{item}")
        dates = [parse_date(row[key]) for key in ("FECHA_CONVOCATORIA", "FECHA_BUENAPRO")]
        if not all(dates) or not row["ENTIDAD"].strip() or not row["PROVEEDOR"].strip():
            raise ValueError(f"Missing SEACE identity/date at row {number}")
        try:
            amount = Decimal(row["MONTO_ADJUDICADO_ITEM_SOLES"])
        except InvalidOperation as exc:
            raise ValueError(f"Invalid SEACE amount at row {number}") from exc
        if (not amount.is_finite() or amount < 0 or not math.isfinite(float(amount))
                or not re.fullmatch(r"[0-9]+", row["CODIGOENTIDAD"])):
            raise ValueError(f"Invalid SEACE amount/entity at row {number}")
        records.append({
            "entity_id": row["CODIGOENTIDAD"], "entity_name": row["ENTIDAD"],
            "government_level": row["TIPOENTIDAD"], "process_id": f"SEACE-{process}",
            "seace_code": row["PROCESO"], "title": row["DESCRIPCION_PROCESO"],
            "object": row["OBJETOCONTRACTUAL"], "selection_method": row["TIPOPROCESOSELECCION"],
            "call_date": dates[0], "award_id": f"SEACE-{process}-ITEM-{item}-RUC-{ruc}",
            "award_title": row["DESCRIPCION_ITEM"], "award_status": row["ESTADO_ITEM"],
            "award_date": dates[1], "amount": str(amount), "currency": "PEN",
            "original_currency": row["MONEDA"], "provider_ruc": ruc,
            "provider_name": row["PROVEEDOR"], "source_row": str(number),
            "source_url": f"{meta['url']}#row={number}",
            "extraction_date": meta["downloaded_at"][:10],
        })
    frame = pd.DataFrame(records)
    frame.attrs = {"source_rows": count, "excluded_rows": count-len(records),
                   "source_dataset": filename, "file_sha256": meta["sha256"]}
    return frame
