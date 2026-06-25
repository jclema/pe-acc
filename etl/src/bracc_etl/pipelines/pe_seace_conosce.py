from __future__ import annotations

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


class PeSeaceConoscePipeline(Pipeline):
    """Minimal MVP pipeline for Peru SEACE/CONOSCE procurement awards."""

    name = "pe_seace_conosce"
    source_id = "seace_conosce"

    def __init__(
        self,
        driver: Driver,
        data_dir: str = "./data",
        limit: int | None = None,
        chunk_size: int = 50_000,
        **kwargs: Any,
    ) -> None:
        super().__init__(driver, data_dir, limit=limit, chunk_size=chunk_size, **kwargs)
        self._raw_rows: pd.DataFrame = pd.DataFrame()
        self.entities: list[dict[str, Any]] = []
        self.providers: list[dict[str, Any]] = []
        self.processes: list[dict[str, Any]] = []
        self.awards: list[dict[str, Any]] = []
        self.entity_process_rels: list[dict[str, Any]] = []
        self.process_award_rels: list[dict[str, Any]] = []
        self.award_provider_rels: list[dict[str, Any]] = []

    def extract(self) -> None:
        candidates = [
            Path(self.data_dir) / "pe" / "seace_conosce" / "processes.csv",
            Path(self.data_dir) / "seace_conosce" / "processes.csv",
        ]
        csv_path = next((path for path in candidates if path.exists()), None)
        if csv_path is None:
            logger.warning("[%s] processes.csv not found in %s", self.name, candidates)
            return
        self._raw_rows = pd.read_csv(csv_path, dtype=str, keep_default_na=False)

    def transform(self) -> None:
        entities: list[dict[str, Any]] = []
        providers: list[dict[str, Any]] = []
        processes: list[dict[str, Any]] = []
        awards: list[dict[str, Any]] = []
        entity_process_rels: list[dict[str, Any]] = []
        process_award_rels: list[dict[str, Any]] = []
        award_provider_rels: list[dict[str, Any]] = []

        for _, row in self._raw_rows.iterrows():
            entity_id = str(row.get("entity_id", "")).strip()
            process_id = str(row.get("process_id", "")).strip()
            award_id = str(row.get("award_id", "")).strip()
            provider_ruc = strip_document(str(row.get("provider_ruc", "")))

            if not entity_id or not process_id or not award_id or len(provider_ruc) != 11:
                continue

            extraction_date = parse_date(str(row.get("extraction_date", "")))
            source_url = str(row.get("source_url", "")).strip()

            entities.append({
                "entity_id": entity_id,
                "name": normalize_name(str(row.get("entity_name", ""))),
                "government_level": str(row.get("government_level", "")).strip().lower(),
                "sector": str(row.get("sector", "")).strip(),
                "ubigeo": strip_document(str(row.get("ubigeo", "")))[:6],
                "source": "seace_conosce",
                "source_url": source_url,
                "extraction_date": extraction_date,
            })

            providers.append({
                "ruc": provider_ruc,
                "legal_name": normalize_name(str(row.get("provider_name", ""))),
                "trade_name": "",
                "source": "seace_conosce",
                "source_url": source_url,
                "extraction_date": extraction_date,
            })

            processes.append({
                "process_id": process_id,
                "seace_code": str(row.get("seace_code", "")).strip(),
                "title": normalize_name(str(row.get("title", ""))),
                "object": normalize_name(str(row.get("object", ""))),
                "selection_method": str(row.get("selection_method", "")).strip(),
                "status": str(row.get("status", "")).strip(),
                "call_date": parse_date(str(row.get("call_date", ""))),
                "source": "seace_conosce",
                "source_url": source_url,
                "extraction_date": extraction_date,
            })

            awards.append({
                "award_id": award_id,
                "award_title": normalize_name(str(row.get("award_title", ""))) or normalize_name(str(row.get("title", ""))),
                "award_date": parse_date(str(row.get("award_date", ""))),
                "amount": float(str(row.get("amount", "0")).replace(",", "") or 0),
                "provider_ruc": provider_ruc,
                "source": "seace_conosce",
                "source_url": source_url,
                "extraction_date": extraction_date,
            })

            entity_process_rels.append({
                "source_key": entity_id,
                "target_key": process_id,
                "source": "seace_conosce",
            })
            process_award_rels.append({
                "source_key": process_id,
                "target_key": award_id,
                "source": "seace_conosce",
            })
            award_provider_rels.append({
                "source_key": award_id,
                "target_key": provider_ruc,
                "source": "seace_conosce",
                "confidence": 1.0,
            })

        if self.limit is not None:
            entities = entities[: self.limit]
            providers = providers[: self.limit]
            processes = processes[: self.limit]
            awards = awards[: self.limit]
            entity_process_rels = entity_process_rels[: self.limit]
            process_award_rels = process_award_rels[: self.limit]
            award_provider_rels = award_provider_rels[: self.limit]

        self.rows_in = len(self._raw_rows)
        self.entities = deduplicate_rows(entities, ["entity_id"])
        self.providers = deduplicate_rows(providers, ["ruc"])
        self.processes = deduplicate_rows(processes, ["process_id"])
        self.awards = deduplicate_rows(awards, ["award_id"])
        self.entity_process_rels = entity_process_rels
        self.process_award_rels = process_award_rels
        self.award_provider_rels = award_provider_rels
        self.rows_loaded = len(self.awards)

    def load(self) -> None:
        loader = Neo4jBatchLoader(self.driver)
        if self.entities:
            loader.load_nodes("Entity", self.entities, key_field="entity_id")
        if self.providers:
            loader.load_nodes("Provider", self.providers, key_field="ruc")
        if self.processes:
            loader.load_nodes("ProcurementProcess", self.processes, key_field="process_id")
        if self.awards:
            loader.load_nodes("Award", self.awards, key_field="award_id")

        if self.entity_process_rels:
            loader.load_relationships(
                "PUBLISHED",
                self.entity_process_rels,
                source_label="Entity",
                source_key="entity_id",
                target_label="ProcurementProcess",
                target_key="process_id",
                properties=["source"],
            )
        if self.process_award_rels:
            loader.load_relationships(
                "HAS_AWARD",
                self.process_award_rels,
                source_label="ProcurementProcess",
                source_key="process_id",
                target_label="Award",
                target_key="award_id",
                properties=["source"],
            )
        if self.award_provider_rels:
            loader.load_relationships(
                "WINNER",
                self.award_provider_rels,
                source_label="Award",
                source_key="award_id",
                target_label="Provider",
                target_key="ruc",
                properties=["source", "confidence"],
            )

