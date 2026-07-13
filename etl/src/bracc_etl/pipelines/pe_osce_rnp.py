from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from bracc_etl.base import Pipeline
from bracc_etl.loader import Neo4jBatchLoader
from bracc_etl.transforms import normalize_name, strip_document

if TYPE_CHECKING:
    from neo4j import Driver

logger = logging.getLogger(__name__)

# Same OSCE Confluence page as pe_osce_sanctions.py, different attachments:
# the RNP (Registro Nacional de Proveedores) ownership network.
_CONFLUENCE_BASE_URL = os.getenv(
    "PE_OSCE_CONFLUENCE_BASE_URL", "https://osce-gob-pe.atlassian.net/wiki",
)
_CONFLUENCE_PAGE_ID = os.getenv("PE_OSCE_CONFLUENCE_PAGE_ID", "106889269")
_SOCIOS_ATTACHMENT_NAME = "Socios.csv"
_REPRESENTANTES_ATTACHMENT_NAME = "representantes.csv"
_ORGANOS_ATTACHMENT_NAME = "organos.csv"
_ALL_ATTACHMENT_NAMES = (
    _SOCIOS_ATTACHMENT_NAME,
    _REPRESENTANTES_ATTACHMENT_NAME,
    _ORGANOS_ATTACHMENT_NAME,
)
_HTTP_USER_AGENT = "Mozilla/5.0 (compatible; PEACC-etl/1.0)"
_HTTP_TIMEOUT_SEC = 120.0


class PeOsceRnpPipeline(Pipeline):
    """Peru OSCE RNP ownership network (Socios/Representantes/Organos).

    Links the people (or companies) behind each state contractor to the same
    Provider nodes pe_osce_sanctions.py already creates, via SOCIO_DE,
    REPRESENTA_A and MIEMBRO_ORGANO_DE. Person nodes are gated by the
    existing PUBLIC_ALLOW_PERSON policy (public_guard.py) same as Brazil's.
    """

    name = "pe_osce_rnp"
    source_id = "osce_rnp"

    def __init__(
        self,
        driver: Driver,
        data_dir: str = "./data",
        limit: int | None = None,
        chunk_size: int = 50_000,
        source_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(driver, data_dir, limit=limit, chunk_size=chunk_size, **kwargs)
        self.raw_files: list[Path] = []
        self.persons: list[dict[str, Any]] = []
        self.companies: list[dict[str, Any]] = []
        self.socio_de: list[dict[str, Any]] = []
        self.representa_a: list[dict[str, Any]] = []
        self.miembro_organo_de: list[dict[str, Any]] = []
        self.source_mode = source_mode or os.getenv("PE_OSCE_SOURCE_MODE", "file")

    def extract(self) -> None:
        if self.source_mode == "api":
            try:
                self._extract_via_api()
                return
            except Exception as exc:  # noqa: BLE001 - any API failure must fall back to file mode
                logger.warning(
                    "[%s] API fetch failed (%s); falling back to file mode", self.name, exc,
                )
        self._extract_from_local_files()

    def _extract_via_api(self) -> None:
        import httpx

        headers = {"User-Agent": _HTTP_USER_AGENT, "Accept": "application/json"}
        listing_url = (
            f"{_CONFLUENCE_BASE_URL}/rest/api/content/{_CONFLUENCE_PAGE_ID}"
            "/child/attachment?limit=50"
        )
        response = httpx.get(listing_url, headers=headers, timeout=_HTTP_TIMEOUT_SEC)
        response.raise_for_status()
        attachments = response.json().get("results", [])

        wanted: dict[str, str | None] = dict.fromkeys(_ALL_ATTACHMENT_NAMES)
        for attachment in attachments:
            title = attachment.get("title", "")
            if title in wanted:
                wanted[title] = attachment.get("_links", {}).get("download")

        raw_dir = Path(self.data_dir) / "raw" / "pe" / "osce_rnp"
        raw_dir.mkdir(parents=True, exist_ok=True)

        downloaded: list[Path] = []
        for filename, download_path in wanted.items():
            if not download_path:
                logger.warning("[%s] attachment not found via API: %s", self.name, filename)
                continue
            file_response = httpx.get(
                f"{_CONFLUENCE_BASE_URL}{download_path}",
                headers={"User-Agent": _HTTP_USER_AGENT},
                timeout=_HTTP_TIMEOUT_SEC,
                follow_redirects=True,
            )
            file_response.raise_for_status()
            dest = raw_dir / filename
            dest.write_bytes(file_response.content)
            downloaded.append(dest)

        if not downloaded:
            msg = "No OSCE RNP attachments found via Confluence API"
            raise RuntimeError(msg)

        logger.info("[%s] fetched %d file(s) via API", self.name, len(downloaded))
        self.raw_files = sorted(downloaded)

    def _extract_from_local_files(self) -> None:
        raw_dir = Path(self.data_dir) / "raw" / "pe" / "osce_rnp"
        if not raw_dir.exists():
            logger.warning("[%s] raw RNP directory not found: %s", self.name, raw_dir)
            return
        self.raw_files = sorted(
            path
            for path in raw_dir.iterdir()
            if path.is_file() and path.suffix.lower() == ".csv" and path.name != ".gitkeep"
        )
        if not self.raw_files:
            logger.warning("[%s] no RNP files found in %s", self.name, raw_dir)

    def transform(self) -> None:
        persons: dict[str, dict[str, Any]] = {}
        companies: dict[str, dict[str, Any]] = {}
        socio_de: list[dict[str, Any]] = []
        representa_a: list[dict[str, Any]] = []
        miembro_organo_de: list[dict[str, Any]] = []
        rows_in = 0
        rows_loaded = 0

        for file_path in self.raw_files:
            kind = self._kind_for_file(file_path.name)
            if kind is None:
                continue
            df = pd.read_csv(
                file_path,
                dtype=str,
                keep_default_na=False,
                encoding="latin-1",
                sep="|",
                on_bad_lines="warn",
            )
            rows_in += len(df)
            for _, row in df.iterrows():
                raw_row = row.to_dict()
                relationship = self._process_row(raw_row, kind, persons, companies)
                if relationship is None:
                    continue
                if kind == "socio":
                    socio_de.append(relationship)
                elif kind == "representante":
                    representa_a.append(relationship)
                else:
                    miembro_organo_de.append(relationship)
                rows_loaded += 1
                if self.limit is not None and rows_loaded >= self.limit:
                    break
            if self.limit is not None and rows_loaded >= self.limit:
                break

        self.rows_in = rows_in
        self.persons = list(persons.values())
        self.companies = list(companies.values())
        self.socio_de = socio_de
        self.representa_a = representa_a
        self.miembro_organo_de = miembro_organo_de
        self.rows_loaded = rows_loaded

    def _process_row(
        self,
        row: dict[str, Any],
        kind: str,
        persons: dict[str, dict[str, Any]],
        companies: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        ruc_proveedor = strip_document(self._first_value(row, "Ruc_Proveedor"))
        if len(ruc_proveedor) != 11:
            return None
        doc = strip_document(self._first_value(row, "Nro_Documento"))
        name = normalize_name(
            self._first_value(row, "Nombre_RazonSocial", "Nombre_o_RazonSocial"),
        )
        if not doc or not name:
            return None

        # Placeholder for the target company: never overwrites a richer
        # Provider record (e.g. one already loaded by pe_osce_sanctions.py).
        companies.setdefault(ruc_proveedor, {"ruc": ruc_proveedor, "source": "osce_rnp"})

        if len(doc) == 11:
            source_label = "Provider"
            companies[doc] = {
                "ruc": doc,
                "legal_name": name,
                "name": name,
                "source": "osce_rnp",
            }
        elif len(doc) == 8:
            source_label = "Person"
            persons[doc] = {"dni": doc, "name": name, "source": "osce_rnp"}
        else:
            # Foreign IDs / other formats: skip in this first pass rather than
            # guess an identity.
            return None

        relationship = {
            "source_key": doc,
            "target_key": ruc_proveedor,
            "source": "osce_rnp",
            "_label": source_label,
        }
        if kind == "organo":
            relationship["cargo"] = self._first_value(row, "Cargo")
        return relationship

    @staticmethod
    def _kind_for_file(filename: str) -> str | None:
        lower = filename.lower()
        if lower == "socios.csv":
            return "socio"
        if "representante" in lower:
            return "representante"
        if "organo" in lower:
            return "organo"
        return None

    @staticmethod
    def _first_value(row: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return ""

    def load(self) -> None:
        loader = Neo4jBatchLoader(self.driver, batch_size=min(self.chunk_size, 20_000))
        if self.persons:
            loader.load_nodes("Person", self.persons, key_field="dni")
        if self.companies:
            loader.load_nodes("Provider", self.companies, key_field="ruc")
        self._load_rel(loader, "SOCIO_DE", self.socio_de)
        self._load_rel(loader, "REPRESENTA_A", self.representa_a)
        self._load_rel(loader, "MIEMBRO_ORGANO_DE", self.miembro_organo_de, extra_props=["cargo"])

    @staticmethod
    def _load_rel(
        loader: Neo4jBatchLoader,
        rel_type: str,
        rows: list[dict[str, Any]],
        extra_props: list[str] | None = None,
    ) -> None:
        properties = ["source", *(extra_props or [])]
        person_rows = [r for r in rows if r["_label"] == "Person"]
        company_rows = [r for r in rows if r["_label"] == "Provider"]
        if person_rows:
            loader.load_relationships(
                rel_type,
                person_rows,
                source_label="Person",
                source_key="dni",
                target_label="Provider",
                target_key="ruc",
                properties=properties,
            )
        if company_rows:
            loader.load_relationships(
                rel_type,
                company_rows,
                source_label="Provider",
                source_key="ruc",
                target_label="Provider",
                target_key="ruc",
                properties=properties,
            )
