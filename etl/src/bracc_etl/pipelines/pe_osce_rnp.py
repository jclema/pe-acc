from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bracc_etl.base import Pipeline
from bracc_etl.loader import Neo4jBatchLoader
from bracc_etl.transforms import normalize_name

if TYPE_CHECKING:
    from neo4j import Driver

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
CONSOLIDATED = "conformacion_juridica.csv"
CURRENT_COLUMNS = {
    "FECHA_CORTE", "TIPO_DOCUMENTO", "NUMERO_DOCUMENTO", "NOMBRE_RAZONODENOMINACIONSOCIAL",
    "RUC", "TIPO_CONF_JURIDICA", "FECHA_INICIO_VIGENCIA", "ID_FORMA_SOCIETARIA",
    "DE_FORMA_SOCIETARIA",
}
CURRENT_TYPES = {"SOCIO_ACCIONISTA_TITULAR": "SOCIO_DE", "REPRESENTANTE_LEGAL": "REPRESENTA_A",
                 "ORGANO_ADMINISTRACION": "MIEMBRO_ORGANO_DE"}


def read_rnp(path: Path, *, limit: int | None = None) -> tuple[list[dict[str, str]], int]:
    """Read an ANSI export; reject identities without deleting document characters."""
    current = path.name == CONSOLIDATED
    relationship, name_column = ("", "Nombre_RazonSocial") if current else FILES[path.name]
    required = {"Tipo_Documento", "Nro_Documento", "Ruc_Proveedor", name_column}
    if path.name == "organos.csv":
        required.add("Cargo")
    with path.open("rb") as binary:
        digest = hashlib.file_digest(binary, "sha256").hexdigest()
    records: list[dict[str, str]] = []
    count = 0
    with path.open(encoding="cp1252", errors="surrogateescape" if current else "strict",
                   newline="") as stream:
        header = stream.readline()
        delimiter = max(("|", ","), key=header.count)
        stream.seek(0)
        reader = csv.DictReader(stream, delimiter=delimiter, strict=True)
        columns = reader.fieldnames or []
        expected = CURRENT_COLUMNS if current else required
        if not expected.issubset(columns) or len(columns) != len(set(columns)):
            raise ValueError(f"{path}: missing or duplicate RNP columns")
        if limit == 0:
            return [], 0
        for row in reader:
            count += 1
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{path}:{reader.line_num}: malformed RNP row")
            if any(re.search(r"[\udc80-\udcff]", value) for value in row.values()):
                continue  # Undefined ANSI bytes: retain raw evidence, never invent a name.
            evidence = {}
            if current:
                if row["TIPO_CONF_JURIDICA"] not in CURRENT_TYPES:
                    raise ValueError("Unknown consolidated RNP relationship")
                relationship = CURRENT_TYPES[row["TIPO_CONF_JURIDICA"]]
                # Current public review scope: corporate declarations only.
                if (row["TIPO_DOCUMENTO"] != "REG. UNICO DE CONTRIBUYENTES"
                        or not re.fullmatch(r"20[0-9]{9}", row["NUMERO_DOCUMENTO"])):
                    continue
                evidence = {
                    "source_cutoff": (datetime.strptime(row["FECHA_CORTE"], "%Y%m%d")
                                      .date().isoformat()),
                    "valid_from": (datetime.strptime(row["FECHA_INICIO_VIGENCIA"], "%Y%m%d")
                                   .date().isoformat() if row["FECHA_INICIO_VIGENCIA"] else ""),
                    "source_row": str(reader.line_num),
                }
                row = {"Tipo_Documento": row["TIPO_DOCUMENTO"],
                       "Nro_Documento": row["NUMERO_DOCUMENTO"], "Ruc_Proveedor": row["RUC"],
                       name_column: row["NOMBRE_RAZONODENOMINACIONSOCIAL"]}
            document = row["Nro_Documento"].strip()
            target = row["Ruc_Proveedor"].strip()
            name = normalize_name(row[name_column])
            identity = DOCUMENTS.get(row["Tipo_Documento"].strip().upper())
            if identity is None or not name or not re.fullmatch(r"20[0-9]{9}", target):
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
                    **evidence,
                }
            )
            if limit is not None and len(records) >= limit:
                break
    return records, count


class PeOsceRnpPipeline(Pipeline):
    name = "pe_osce_rnp"
    source_id = "osce_rnp"

    def __init__(self, driver: Driver, data_dir: str = "./data", **kwargs: Any) -> None:
        super().__init__(driver, data_dir, **kwargs)
        if self.chunk_size <= 0 or (self.limit is not None and self.limit < 0):
            raise ValueError("chunk_size must be positive and limit nonnegative")
        self.raw_files: list[Path] = []
        self.records: list[dict[str, str]] = []

    def extract(self) -> None:
        directory = Path(self.data_dir) / "raw" / "pe" / "osce_rnp"
        current = directory / CONSOLIDATED
        self.raw_files = ([current] if current.exists()
                          else [directory / filename for filename in FILES])
        for path in self.raw_files:
            if not path.is_file():
                raise FileNotFoundError(path)

    def transform(self) -> None:
        self.records = []
        self.rows_in = 0
        for path in self.raw_files:
            rows, count = read_rnp(path, limit=self.limit if path.name == CONSOLIDATED else None)
            self.rows_in += count
            self.records.extend(rows)
        self.records = self.records[: self.limit]
        for row in self.records:
            components = [
                row[key] for key in ("label", "key", "document", "target", "type", "cargo", "name")
            ]
            if "source_cutoff" in row:
                components.extend([row["source_cutoff"], row["valid_from"]])
            row["record_id"] = hashlib.sha256(json.dumps(components).encode()).hexdigest()
        self.rows_loaded = len({row["record_id"] for row in self.records})

    def load(self) -> None:
        loader = Neo4jBatchLoader(
            self.driver,
            batch_size=self.chunk_size,
            neo4j_database=self.neo4j_database,
        )
        providers: list[dict[str, Any]] = []
        for row in self.records:
            evidence = {key: row[key] for key in ("source_url", "source_dataset", "file_sha256")}
            providers.append({"ruc": row["target"], **evidence})
            if row["label"] == "Provider":
                providers.append({"ruc": row["document"], "name": row["name"], **evidence})
        loader.load_provider_records(providers, self.source_id)
        for relationship, _ in FILES.values():
            for label, key in (("Person", "dni"), ("Person", "ruc"), ("Provider", "ruc")):
                rows = [
                    row
                    for row in self.records
                    if (row["type"], row["label"], row["key"]) == (relationship, label, key)
                ]
                loader.run_query(
                    f"UNWIND $rows AS row MERGE (a:{label} {{{key}: row.document}}) "
                    "ON CREATE SET a.source = row.source, a.source_url = row.source_url "
                    "SET a.name = coalesce(a.name, a.legal_name, row.name) "
                    "MERGE (b:Provider {ruc: row.target}) "
                    "ON CREATE SET b.source = row.source, b.source_url = row.source_url "
                    f"MERGE (a)-[r:{relationship} {{record_id: row.record_id}}]->(b) "
                    "SET r.source = row.source, r.source_dataset = row.source_dataset, "
                    "r.source_url = row.source_url, r.file_sha256 = row.file_sha256, "
                    "r.declared_name = row.name, r.cargo = row.cargo, "
                    "r.source_cutoff = row.source_cutoff, r.valid_from = row.valid_from, "
                    "r.source_row = row.source_row",
                    rows,
                )
