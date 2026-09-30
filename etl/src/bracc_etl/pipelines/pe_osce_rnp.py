from __future__ import annotations

import csv
import hashlib
import re
from typing import TYPE_CHECKING

from bracc_etl.transforms import normalize_name

if TYPE_CHECKING:
    from pathlib import Path

SOURCE_URL = "https://osce-gob-pe.atlassian.net/wiki/spaces/PNDA/pages/106889267"
FILES = {
    "Socios.csv": ("SOCIO_DE", "Nombre_o_RazonSocial"),
    "representantes.csv": ("REPRESENTA_A", "Nombre_RazonSocial"),
    "organos.csv": ("MIEMBRO_ORGANO_DE", "Nombre_RazonSocial"),
}
DOCUMENTS = {
    "DOC. NACIONAL DE IDENTIDAD/LE": ("Person", "dni", 8),
    "DOC. NACIONAL DE IDENTIDAD": ("Person", "dni", 8),
    "REG. UNICO DE CONTRIBUYENTES": ("Provider", "ruc", 11),
}


def read_rnp(path: Path) -> tuple[list[dict[str, str]], int]:
    """Read an ANSI export; reject identities without deleting document characters."""
    relationship, name_column = FILES[path.name]
    required = {"Tipo_Documento", "Nro_Documento", "Ruc_Proveedor", name_column}
    if path.name == "organos.csv":
        required.add("Cargo")
    with path.open("rb") as binary:
        digest = hashlib.file_digest(binary, "sha256").hexdigest()
    records: list[dict[str, str]] = []
    count = 0
    with path.open(encoding="cp1252", newline="") as stream:
        header = stream.readline()
        delimiter = max(("|", ","), key=header.count)
        stream.seek(0)
        reader = csv.DictReader(stream, delimiter=delimiter, strict=True)
        columns = reader.fieldnames or []
        if not required.issubset(columns) or len(columns) != len(set(columns)):
            raise ValueError(f"{path}: missing or duplicate RNP columns")
        for row in reader:
            count += 1
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{path}:{reader.line_num}: malformed RNP row")
            document = row["Nro_Documento"].strip()
            target = row["Ruc_Proveedor"].strip()
            name = normalize_name(row[name_column])
            identity = DOCUMENTS.get(row["Tipo_Documento"].strip().upper())
            if identity is None or not name or not re.fullmatch(r"(?:10|15|17|20)[0-9]{9}", target):
                continue
            label, key, length = identity
            if not re.fullmatch(rf"[0-9]{{{length}}}", document):
                continue
            if key == "ruc":
                if not re.fullmatch(r"(?:10|15|17|20)[0-9]{9}", document):
                    continue
                if not document.startswith("20"):
                    label = "Person"
            records.append(
                {
                    "label": label,
                    "key": key,
                    "document": document,
                    "target": target,
                    "name": name,
                    "cargo": row.get("Cargo", "").strip(),
                    "type": relationship,
                    "source": "osce_rnp",
                    "source_dataset": path.name,
                    "source_url": SOURCE_URL,
                    "file_sha256": digest,
                }
            )
    return records, count
