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


class PeSunatRucPipeline(Pipeline):
    """Minimal MVP pipeline for Peru SUNAT provider identity data."""

    name = "pe_sunat_ruc"
    source_id = "sunat_ruc"

    def __init__(
        self,
        driver: Driver,
        data_dir: str = "./data",
        limit: int | None = None,
        chunk_size: int = 50_000,
        **kwargs: Any,
    ) -> None:
        super().__init__(driver, data_dir, limit=limit, chunk_size=chunk_size, **kwargs)
        self._raw_providers: pd.DataFrame = pd.DataFrame()
        self.providers: list[dict[str, Any]] = []
        self.raw_csv_path: Path | None = None
        self.normalized_csv_path: Path | None = None

    def extract(self) -> None:
        raw_dir_candidates = [
            Path(self.data_dir) / "raw" / "pe" / "sunat_ruc",
            Path(self.data_dir) / "pe" / "sunat_ruc",
            Path(self.data_dir) / "sunat_ruc",
        ]
        raw_dir = next((path for path in raw_dir_candidates if path.exists() and path.is_dir()), None)
        if raw_dir is None:
            logger.warning("[%s] raw SUNAT directory not found in %s", self.name, raw_dir_candidates)
            return

        raw_csv_candidates = sorted([path for path in raw_dir.iterdir() if path.is_file() and path.suffix.lower() == ".csv"])
        self.raw_csv_path = next((path for path in raw_csv_candidates if path.name != "providers.csv"), None)
        if self.raw_csv_path is not None:
            return

        normalized_candidates = [
            Path(self.data_dir) / "normalized" / "pe" / "sunat_ruc" / "providers_normalized.csv",
            Path(self.data_dir) / "pe" / "sunat_ruc" / "providers.csv",
            Path(self.data_dir) / "sunat_ruc" / "providers.csv",
        ]
        self.normalized_csv_path = next((path for path in normalized_candidates if path.exists()), None)
        if self.normalized_csv_path is not None:
            self._raw_providers = pd.read_csv(
                self.normalized_csv_path,
                dtype=str,
                keep_default_na=False,
            )
            return

        logger.warning("[%s] raw SUNAT csv not found in %s", self.name, raw_dir)

    def transform(self) -> None:
        if self._raw_providers.empty and self.raw_csv_path is not None:
            self._transform_raw_csv()
            return

        providers: list[dict[str, Any]] = []
        for _, row in self._raw_providers.iterrows():
            provider = self._normalize_provider_row(row.to_dict())
            if provider is None:
                continue
            providers.append(provider)

        if self.limit is not None:
            providers = providers[: self.limit]
        self.rows_in = len(self._raw_providers)
        self.providers = deduplicate_rows(providers, ["ruc"])
        self.rows_loaded = len(self.providers)

    def load(self) -> None:
        if self.providers:
            loader = Neo4jBatchLoader(self.driver, batch_size=min(self.chunk_size, 20_000))
            loader.load_nodes("Provider", self.providers, key_field="ruc")
            return

        if self.normalized_csv_path is None or not self.normalized_csv_path.exists():
            return

        loader = Neo4jBatchLoader(self.driver, batch_size=min(self.chunk_size, 20_000))
        for chunk in pd.read_csv(
            self.normalized_csv_path,
            dtype=str,
            keep_default_na=False,
            chunksize=self.chunk_size,
        ):
            rows = chunk.to_dict(orient="records")
            loader.load_nodes("Provider", rows, key_field="ruc")

    def _normalize_provider_row(self, raw_row: dict[str, Any]) -> dict[str, Any] | None:
        raw_ruc = self._first_value(raw_row, "ruc", "RUC")
        ruc_digits = strip_document(str(raw_ruc))
        if len(ruc_digits) != 11:
            return None

        legal_name = normalize_name(
            self._first_value(
                raw_row,
                "legal_name",
                "LEGAL_NAME",
                "razon_social",
                "RAZON_SOCIAL",
                "nombre_o_razon_social",
                "NOMBRE_O_RAZON_SOCIAL",
            ),
        )
        provider_type = str(self._first_value(raw_row, "provider_type", "Tipo", "TIPO")).strip()
        if not legal_name:
            legal_name = f"RUC {ruc_digits}"

        extraction_date = self._parse_extraction_date(
            self._first_value(
                raw_row,
                "extraction_date",
                "EXTRACTION_DATE",
                "PERIODO_PUBLICACION",
            ),
        )

        source_url = str(self._first_value(raw_row, "source_url", "SOURCE_URL")).strip()
        source_dataset = str(
            self._first_value(raw_row, "source_dataset", "SOURCE_DATASET")
            or (self.raw_csv_path.name if self.raw_csv_path else "")
        ).strip()

        # Keep the Provider payload intentionally lean for the first Peru MVP.
        # The search and provider detail flows currently need identity,
        # status, geography, and provenance much more than the full SUNAT row.
        return {
            "ruc": ruc_digits,
            "legal_name": legal_name,
            "name": legal_name,
            "trade_name": normalize_name(self._first_value(raw_row, "trade_name", "TRADE_NAME")),
            "tax_status": str(self._first_value(raw_row, "tax_status", "Estado", "ESTADO")).strip(),
            "tax_condition": str(self._first_value(raw_row, "tax_condition", "Condicion", "CONDICION")).strip(),
            "provider_type": provider_type,
            "ubigeo": strip_document(str(self._first_value(raw_row, "ubigeo", "UBIGEO")))[:6],
            "department": normalize_name(self._first_value(raw_row, "department", "Departamento")),
            "province": normalize_name(self._first_value(raw_row, "province", "Provincia")),
            "district": normalize_name(self._first_value(raw_row, "district", "Distrito")),
            "source": "sunat_ruc",
            "source_dataset": source_dataset,
            "source_url": source_url,
            "extraction_date": extraction_date,
        }

    def _transform_raw_csv(self) -> None:
        if self.raw_csv_path is None:
            return

        normalized_dir = Path(self.data_dir) / "normalized" / "pe" / "sunat_ruc"
        normalized_dir.mkdir(parents=True, exist_ok=True)
        self.normalized_csv_path = normalized_dir / "providers_normalized.csv"

        seen_rucs: set[str] = set()
        rows_written = 0
        rows_in = 0
        wrote_header = False

        with self.normalized_csv_path.open("w", encoding="utf-8", newline="") as out_file:
            writer: csv.DictWriter[str] | None = None

            for chunk in pd.read_csv(
                self.raw_csv_path,
                dtype=str,
                keep_default_na=False,
                encoding="latin-1",
                chunksize=self.chunk_size,
            ):
                rows_in += len(chunk)
                normalized_rows: list[dict[str, Any]] = []
                for row in chunk.to_dict(orient="records"):
                    provider = self._normalize_provider_row(row)
                    if provider is None or provider["ruc"] in seen_rucs:
                        continue
                    seen_rucs.add(provider["ruc"])
                    normalized_rows.append(provider)
                    rows_written += 1
                    if self.limit is not None and rows_written >= self.limit:
                        break

                if normalized_rows:
                    if writer is None:
                        writer = csv.DictWriter(out_file, fieldnames=list(normalized_rows[0].keys()))
                    if not wrote_header:
                        writer.writeheader()
                        wrote_header = True
                    writer.writerows(normalized_rows)

                if self.limit is not None and rows_written >= self.limit:
                    break

        self.rows_in = rows_in
        self.rows_loaded = rows_written
        logger.info(
            "[%s] normalized %d provider rows into %s",
            self.name,
            rows_written,
            self.normalized_csv_path,
        )

    @staticmethod
    def _first_value(row: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    @staticmethod
    def _parse_extraction_date(value: str) -> str:
        value = str(value).strip()
        if len(value) == 6 and value.isdigit():
            return f"{value[:4]}-{value[4:6]}-01"
        return parse_date(value)
