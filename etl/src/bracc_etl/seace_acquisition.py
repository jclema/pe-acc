"""Download one official SEACE/CONOSCE awards workbook; never load or normalize rows."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]
from defusedxml.ElementTree import ParseError, fromstring, iterparse  # type: ignore[import-untyped]

ROOT = "https://conosce.osce.gob.pe/buscador/assets/67ae6c4a/reportes"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
MAX_BYTES = 32 * 1024**2
COLUMNS = [
    'CODIGOENTIDAD', 'ENTIDAD_RUC', 'ENTIDAD', 'TIPOENTIDAD', 'ENTIDAD_DEPARTAMENTO',
    'CODIGOCONVOCATORIA', 'OBJETOCONTRACTUAL', 'TIPOPROCESOSELECCION', 'PROCESO',
    'DESCRIPCION_PROCESO', 'N_ITEM', 'DESCRIPCION_ITEM', 'ESTADO_ITEM',
    'CANTIDAD_ADJUDICADO_ITEM', 'MONTO_REFERENCIAL_ITEM_SOLES', 'MONTO_ADJUDICADO_ITEM_SOLES',
    'DEPARTAMENTO_ITEM', 'MONEDA', 'UNIDAD_MEDIDA', 'RUC PROVEEDOR', 'PROVEEDOR',
    'TIPO_PROVEEDOR', 'FECHA_CONVOCATORIA', 'FECHA_BUENAPRO', 'FECHA_CONSENTIMIENTO_BP'
]


def _filename(year: int) -> str:
    if type(year) is not int or not 2018 <= year <= datetime.now(UTC).year:
        raise ValueError("SEACE year must be within the published 2018-current range")
    return f"CONOSCE_ADJUDICACIONES{year}_0.xlsx"


def validate_workbook(path: Path) -> None:
    """Check bounded ZIP/CRC, XML, header contract and at least one data row."""
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if (len(infos) > 256 or len({i.filename for i in infos}) != len(infos)
                    or sum(i.file_size for i in infos) > 512*1024**2 or archive.testzip()):
                raise ValueError("Invalid or oversized SEACE workbook archive")
            required = {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml",
                        "xl/_rels/workbook.xml.rels", "xl/worksheets/sheet1.xml",
                        "xl/sharedStrings.xml"}
            if not required.issubset(archive.namelist()):
                raise ValueError("Incomplete SEACE XLSX package")
            book = fromstring(archive.read("xl/workbook.xml"))
            sheet = book.find(f"{NS}sheets/{NS}sheet")
            rels = fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            relation = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            if sheet is None or not any(
                r.get("Id") == sheet.get(relation) and r.get("Target") == "worksheets/sheet1.xml"
                for r in rels
            ):
                raise ValueError("Unexpected SEACE worksheet reference")
            strings: list[str] = []
            with archive.open("xl/sharedStrings.xml") as stream:
                for _, element in iterparse(stream, events=("end",)):
                    if element.tag == f"{NS}si":
                        if len(strings) < len(COLUMNS):
                            strings.append("".join(element.itertext()))
                        element.clear()
            header: list[str] = []
            count = 0
            with archive.open("xl/worksheets/sheet1.xml") as stream:
                for _, element in iterparse(stream, events=("end",)):
                    if element.tag != f"{NS}row":
                        continue
                    cells = element.findall(f"{NS}c")
                    if not header:
                        for cell in cells:
                            value = cell.findtext(f"{NS}v", "")
                            if cell.get("t") != "s":
                                raise ValueError("SEACE header must use shared strings")
                            header.append(strings[int(value)])
                        if header != COLUMNS:
                            raise ValueError("Changed or duplicate SEACE workbook columns")
                    elif any(cell.findtext(f"{NS}v", "") for cell in cells):
                        count += 1
                    element.clear()
            if not header or not count:
                raise ValueError("SEACE workbook has no data rows")
    except (zipfile.BadZipFile, KeyError, IndexError, ParseError, DefusedXmlException) as exc:
        raise ValueError("Invalid SEACE workbook") from exc


def valid_snapshot(path: Path) -> bool:
    try:
        if path.is_symlink() or any(p.is_symlink() or not p.is_file() for p in path.iterdir()):
            return False
        meta = json.loads((path / "manifest.json").read_text())
        filename = _filename(meta["year"])
        if {p.name for p in path.iterdir()} != {filename, "manifest.json"}:
            return False
        stamp = datetime.fromisoformat(meta["downloaded_at"])
        if (stamp.tzinfo is None or stamp > datetime.now(UTC)
                or meta["mode"] != "official_xlsx_download"
                or meta["url"] != f"{ROOT}/adjudicaciones/{meta['year']}/{filename}"):
            return False
        file = path / filename
        if not 0 < file.stat().st_size == meta["bytes"] <= MAX_BYTES:
            return False
        with file.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != meta["sha256"]:
                return False
        validate_workbook(file)
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def acquire(root: Path, year: int) -> Path:
    filename = _filename(year)
    url = f"{ROOT}/adjudicaciones/{year}/{filename}"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix="pending-") as directory:
        staging = Path(directory)
        path = staging / filename
        with (httpx.Client(timeout=60, follow_redirects=False) as client,
              client.stream("GET", url) as response, path.open("wb") as stream):
            response.raise_for_status()
            count = 0
            for chunk in response.iter_bytes():
                count += len(chunk)
                if count > MAX_BYTES:
                    raise ValueError("SEACE workbook exceeds bounded download size")
                stream.write(chunk)
            if (not count or response.headers.get("content-length") is not None
                    and count != int(response.headers["content-length"])):
                raise ValueError("Empty or truncated SEACE workbook")
            modified = response.headers.get("last-modified")
        validate_workbook(path)
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        manifest = {"mode": "official_xlsx_download", "year": year, "url": url,
                    "downloaded_at": datetime.now(UTC).isoformat(), "last_modified": modified,
                    "source_cutoff": None, "license": "unspecified", "bytes": count,
                    "sha256": digest, "limitations": "Awards only; not normalized processes.csv"}
        (staging / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        snapshot = staging.with_name(staging.name.replace("pending-", "snapshot-", 1))
        staging.rename(snapshot)
        return snapshot


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    print(acquire(args.output_dir, args.year))
