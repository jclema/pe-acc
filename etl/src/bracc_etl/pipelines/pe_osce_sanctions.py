from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from bracc_etl.base import Pipeline
from bracc_etl.loader import Neo4jBatchLoader
from bracc_etl.transforms import deduplicate_rows, normalize_name, parse_date, strip_document

if TYPE_CHECKING:
    from neo4j import Driver

logger = logging.getLogger(__name__)


class PeOsceSanctionsPipeline(Pipeline):
    """Minimal MVP pipeline for Peru OSCE sanctions linked by provider RUC."""

    name = "pe_osce_sanctions"
    source_id = "osce_sanctions"

    def __init__(
        self,
        driver: Driver,
        data_dir: str = "./data",
        limit: int | None = None,
        chunk_size: int = 50_000,
        **kwargs: Any,
    ) -> None:
        super().__init__(driver, data_dir, limit=limit, chunk_size=chunk_size, **kwargs)
        self._raw_sanctions: pd.DataFrame = pd.DataFrame()
        self.providers: list[dict[str, Any]] = []
        self.sanctions: list[dict[str, Any]] = []
        self.provider_sanctions: list[dict[str, Any]] = []
        self.raw_files: list[Path] = []
        self.normalized_csv_path: Path | None = None

    def extract(self) -> None:
        raw_dir_candidates = [
            Path(self.data_dir) / "raw" / "pe" / "osce_sanctions",
            Path(self.data_dir) / "pe" / "osce_sanctions",
            Path(self.data_dir) / "osce_sanctions",
        ]
        raw_dir = next((path for path in raw_dir_candidates if path.exists() and path.is_dir()), None)
        if raw_dir is None:
            logger.warning("[%s] raw sanctions directory not found in %s", self.name, raw_dir_candidates)
            return
        self.raw_files = sorted(
            [
                path for path in raw_dir.iterdir()
                if path.is_file() and path.suffix.lower() == ".csv" and path.name != ".gitkeep"
            ],
        )
        if not self.raw_files:
            logger.warning("[%s] no sanction files found in %s", self.name, raw_dir)
            return

    def transform(self) -> None:
        if self.raw_files:
            self._transform_raw_files()
            return

        providers: list[dict[str, Any]] = []
        sanctions: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []

        for idx, row in self._raw_sanctions.iterrows():
            provider, sanction, relationship = self._normalize_sanction_row(row.to_dict(), idx)
            if provider is None or sanction is None or relationship is None:
                continue
            providers.append(provider)
            sanctions.append(sanction)
            relationships.append(relationship)

        if self.limit is not None:
            providers = providers[: self.limit]
            sanctions = sanctions[: self.limit]
            relationships = relationships[: self.limit]

        self.rows_in = len(self._raw_sanctions)
        self.providers = deduplicate_rows(providers, ["ruc"])
        self.sanctions = deduplicate_rows(sanctions, ["sanction_id"])
        self.provider_sanctions = relationships
        self.rows_loaded = len(self.sanctions)

    def load(self) -> None:
        loader = Neo4jBatchLoader(self.driver, batch_size=min(self.chunk_size, 20_000))
        if self.providers:
            loader.load_nodes("Provider", self.providers, key_field="ruc")
        if self.sanctions:
            loader.load_nodes("Sanction", self.sanctions, key_field="sanction_id")
        if self.provider_sanctions:
            loader.load_relationships(
                "HAS_SANCTION",
                self.provider_sanctions,
                source_label="Provider",
                source_key="ruc",
                target_label="Sanction",
                target_key="sanction_id",
                properties=["source", "confidence"],
            )

    def _transform_raw_files(self) -> None:
        normalized_dir = Path(self.data_dir) / "normalized" / "pe" / "osce_sanctions"
        normalized_dir.mkdir(parents=True, exist_ok=True)
        self.normalized_csv_path = normalized_dir / "sanctions_normalized.csv"

        providers: list[dict[str, Any]] = []
        sanctions: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        rows_in = 0

        for file_path in self.raw_files:
            source_kind = self._source_kind_for_file(file_path.name)
            df = pd.read_csv(
                file_path,
                dtype=str,
                keep_default_na=False,
                encoding="latin-1",
                sep="|",
            )
            rows_in += len(df)
            for idx, row in df.iterrows():
                provider, sanction, relationship = self._normalize_sanction_row(
                    row.to_dict(),
                    idx,
                    source_kind=source_kind,
                    source_file=file_path.name,
                )
                if provider is None or sanction is None or relationship is None:
                    continue
                providers.append(provider)
                sanctions.append(sanction)
                relationships.append(relationship)
                if self.limit is not None and len(sanctions) >= self.limit:
                    break
            if self.limit is not None and len(sanctions) >= self.limit:
                break

        self.rows_in = rows_in
        self.providers = deduplicate_rows(providers, ["ruc"])
        self.sanctions = deduplicate_rows(sanctions, ["sanction_id"])
        self.provider_sanctions = relationships[: self.limit] if self.limit is not None else relationships
        self.rows_loaded = len(self.sanctions)

        with self.normalized_csv_path.open("w", encoding="utf-8", newline="") as f:
            fieldnames = [
                "sanction_id",
                "ruc",
                "provider_name",
                "sanction_source",
                "sanction_scope",
                "sanction_type",
                "sanction_reason",
                "status",
                "start_date",
                "end_date",
                "source_url",
                "source_dataset",
                "extraction_date",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for sanction in self.sanctions:
                writer.writerow(
                    {
                        "sanction_id": sanction.get("sanction_id", ""),
                        "ruc": sanction.get("ruc", ""),
                        "provider_name": sanction.get("provider_name", ""),
                        "sanction_source": sanction.get("sanction_source", ""),
                        "sanction_scope": sanction.get("sanction_scope", ""),
                        "sanction_type": sanction.get("type", ""),
                        "sanction_reason": sanction.get("reason", ""),
                        "status": sanction.get("status", ""),
                        "start_date": sanction.get("date_start", ""),
                        "end_date": sanction.get("date_end", ""),
                        "source_url": sanction.get("source_url", ""),
                        "source_dataset": sanction.get("source_dataset", ""),
                        "extraction_date": sanction.get("extraction_date", ""),
                    },
                )

    def _normalize_sanction_row(
        self,
        raw_row: dict[str, Any],
        idx: int,
        *,
        source_kind: str | None = None,
        source_file: str = "",
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
        doc = strip_document(str(raw_row.get("ruc", raw_row.get("RUC", raw_row.get("RUC_DNI", "")))))
        if len(doc) != 11:
            return None, None, None

        provider_name = normalize_name(
            str(
                raw_row.get(
                    "provider_name",
                    raw_row.get("NOMBRE_RAZONODENOMINACIONSOCIAL", ""),
                ),
            ),
        ) or f"RUC {doc}"

        extraction_date = self._parse_extraction_date(
            str(raw_row.get("extraction_date", raw_row.get("FECHA_CORTE", ""))),
        )

        kind = source_kind or "tcp_vigente"
        sanction_source = "OSCE_TCP" if kind == "tcp_vigente" else "PODER_JUDICIAL"
        sanction_scope = "vigente"
        sanction_type = "INHABILITACION"
        sanction_reason = ""

        if kind == "tcp_vigente":
            sanction_type = "TRIBUNAL_CONTRATACIONES"
            sanction_reason = str(raw_row.get("DE_MOTIVO_INFRACCION", "")).strip()
        elif kind == "judicial":
            sanction_type = "MANDATO_JUDICIAL"
            sanction_reason = str(raw_row.get("ORGANO_JURISDICCIONAL", "")).strip()

        resolution = str(raw_row.get("NUMERO_RESOLUCION", raw_row.get("sanction_id", ""))).strip()
        sanction_id = resolution or f"{kind}_{doc}_{idx}"

        provider = {
            "ruc": doc,
            "legal_name": provider_name,
            "name": provider_name,
            "trade_name": "",
            "source": "osce_sanctions",
            "source_url": "",
            "extraction_date": extraction_date,
        }

        sanction = {
            "sanction_id": sanction_id,
            "ruc": doc,
            "provider_name": provider_name,
            "type": sanction_type,
            "reason": sanction_reason,
            "status": "VIGENTE",
            "sanction_source": sanction_source,
            "sanction_scope": sanction_scope,
            "date_start": self._parse_extraction_date(str(raw_row.get("start_date", raw_row.get("FECHA_INICIO", "")))),
            "date_end": self._parse_extraction_date(str(raw_row.get("end_date", raw_row.get("FECHA_FIN", "")))) or None,
            "resolution_number": resolution,
            "source": "osce_sanctions",
            "source_dataset": source_file,
            "source_url": "",
            "extraction_date": extraction_date,
        }

        relationship = {
            "source_key": doc,
            "target_key": sanction_id,
            "source": "osce_sanctions",
            "confidence": 1.0,
        }

        return provider, sanction, relationship

    @staticmethod
    def _source_kind_for_file(filename: str) -> str:
        lower = filename.lower()
        if "judicial" in lower:
            return "judicial"
        return "tcp_vigente"

    @staticmethod
    def _parse_extraction_date(value: str) -> str:
        value = value.strip()
        if len(value) == 8 and value.isdigit():
            return parse_date(value)
        return parse_date(value)
