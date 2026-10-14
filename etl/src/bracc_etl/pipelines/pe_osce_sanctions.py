from __future__ import annotations

import csv
import functools
import hashlib
import json
import logging
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pandas as pd

from bracc_etl.base import Pipeline
from bracc_etl.loader import Neo4jBatchLoader
from bracc_etl.transforms import deduplicate_rows, normalize_name, parse_date, strip_document

if TYPE_CHECKING:
    from neo4j import Driver

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_REGISTRY_PATH = _REPO_ROOT / "docs" / "source_registry_pe_v1.csv"
_SUPPORTED_DELIMITERS = ("|", ",")
_DOCUMENT_COLUMNS = ("ruc", "RUC", "RUC_DNI", "RUC/DNI")
_RESOLUTION_COLUMNS = (
    "resolution_number", "sanction_id", "NUMERO_RESOLUCION", "NumeroResolucion",
)


@functools.lru_cache(maxsize=8)
def _registry_source_url(source_id: str) -> str:
    """Return the registered public page for a source, when available."""
    configured_path = os.getenv("BRACC_SOURCE_REGISTRY_PATH", "").strip()
    registry_path = Path(configured_path) if configured_path else _DEFAULT_REGISTRY_PATH
    if not registry_path.is_absolute():
        registry_path = _REPO_ROOT / registry_path
    if not registry_path.exists():
        logger.warning("[%s] source registry not found at %s", source_id, registry_path)
        return ""

    with registry_path.open(encoding="utf-8", newline="") as registry_file:
        for row in csv.DictReader(registry_file):
            if row.get("source_id") == source_id:
                return (row.get("primary_url") or row.get("last_seen_url") or "").strip()
    return ""


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
        source_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(driver, data_dir, limit=limit, chunk_size=chunk_size, **kwargs)
        self._raw_sanctions: pd.DataFrame = pd.DataFrame()
        self.providers: list[dict[str, Any]] = []
        self.sanctions: list[dict[str, Any]] = []
        self.provider_sanctions: list[dict[str, Any]] = []
        self.raw_files: list[Path] = []
        self.normalized_csv_path: Path | None = None
        self.extraction_status: dict[str, Any] = {}
        try:
            self.snapshot_keep = int(os.getenv("PE_OSCE_SNAPSHOT_KEEP", "3"))
            if self.snapshot_keep < 1:
                raise ValueError
        except ValueError as exc:
            raise ValueError("PE_OSCE_SNAPSHOT_KEEP must be a positive integer") from exc
        self.source_mode = source_mode or os.getenv("PE_OSCE_SOURCE_MODE", "file")
        if self.source_mode not in {"file", "api"}:
            raise ValueError("source_mode must be file or api")

    def extract(self) -> None:
        self.raw_files = []
        self.extraction_status = {}
        if self.source_mode == "api":
            try:
                self._extract_via_api()
                self._report_extraction("api")
                return
            except (httpx.HTTPError, ValueError, OSError) as exc:
                logger.warning("[%s] API failed; using local file fallback (%s)", self.name, exc)
        self._extract_from_local_files()
        self._report_extraction("fallback" if self.source_mode == "api" else "file")
        if self.source_mode == "api" and not self.raw_files:
            raise RuntimeError("OSCE API failed and no local fallback CSVs are available")

    def _extract_via_api(self) -> None:
        base = os.getenv(
            "PE_OSCE_CONFLUENCE_BASE_URL", "https://osce-gob-pe.atlassian.net/wiki",
        ).rstrip("/")
        page = os.getenv("PE_OSCE_CONFLUENCE_PAGE_ID", "106889269")
        wanted = {"sancionados.csv", "inhabilitaciones_judiciales.csv"}
        downloads: dict[str, str] = {}
        url = f"{base}/rest/api/content/{page}/child/attachment?limit=50"
        visited: set[str] = set()
        root = Path(self.data_dir) / "raw" / "pe" / "osce_sanctions" / "api"
        root.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=60, follow_redirects=True, headers={
            "User-Agent": "PEACC-etl/1.0",
        }) as client, tempfile.TemporaryDirectory(dir=root, prefix="pending-") as directory:
            while url:
                if url in visited or len(visited) >= 100:
                    raise ValueError("Invalid OSCE attachment pagination")
                visited.add(url)
                response = client.get(url)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                    raise ValueError("Invalid OSCE attachment listing")
                for attachment in payload["results"]:
                    if not isinstance(attachment, dict):
                        raise ValueError("Invalid OSCE attachment")
                    name = attachment.get("title")
                    if not isinstance(name, str):
                        raise ValueError("Invalid OSCE attachment title")
                    if name in wanted:
                        links = attachment.get("_links", {})
                        if not isinstance(links, dict) or not links.get("download"):
                            raise ValueError("OSCE attachment has no download link")
                        if name in downloads:
                            raise ValueError("Duplicate OSCE attachment")
                        downloads[name] = self._api_url(base, links["download"])
                links = payload.get("_links", {})
                if not isinstance(links, dict):
                    raise ValueError("Invalid OSCE pagination links")
                url = self._api_url(base, links["next"]) if links.get("next") else ""
            if set(downloads) != wanted:
                raise ValueError("OSCE listing is missing required sanctions files")
            staging = Path(directory)
            for name, download in sorted(downloads.items()):
                response = client.get(download)
                response.raise_for_status()
                path = staging / name
                path.write_bytes(response.content)
                rows = self._read_raw_csv(path)
                kind = self._source_kind_for_file(name)
                if rows.empty or not any(
                    self._normalize_sanction_row(
                        {str(key): value for key, value in row.to_dict().items()},
                        i, source_kind=kind,
                    )[0]
                    for i, row in rows.iterrows()
                ):
                    raise ValueError("OSCE download has no valid sanctions")
            manifest = {
                "downloaded_at": datetime.now(UTC).isoformat(),
                "source_page": f"{base}/pages/viewpage.action?pageId={page}",
                "files": {name: {
                    "url": downloads[name], "bytes": (staging / name).stat().st_size,
                    "sha256": hashlib.sha256((staging / name).read_bytes()).hexdigest(),
                } for name in sorted(wanted)},
            }
            (staging / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            snapshot = staging.with_name(staging.name.replace("pending-", "snapshot-", 1))
            staging.rename(snapshot)
            self.raw_files = sorted(snapshot / name for name in wanted)
            try:
                self._prune_snapshots(root, snapshot)
            except OSError as exc:
                logger.warning("[%s] snapshot retention failed: %s", self.name, exc)

    def _report_extraction(self, mode: str) -> None:
        downloaded_at = None
        age = None
        if self.raw_files:
            timestamp = self._snapshot_timestamp(self.raw_files[0].parent)
            if timestamp is not None:
                downloaded_at = timestamp.isoformat()
                age = int((datetime.now(UTC) - timestamp).total_seconds())
        self.extraction_status = {
            "mode": mode, "downloaded_at": downloaded_at, "age_seconds": age,
        }
        log = logger.warning if mode == "fallback" else logger.info
        log("[%s] extraction %s; source cutoff is separate", self.name, self.extraction_status)

    def _prune_snapshots(self, root: Path, current: Path) -> None:
        managed = []
        for path in root.glob("snapshot-*"):
            if self._snapshot_timestamp(path) is not None:
                managed.append(path)
        older = sorted((p for p in managed if p != current),
                       key=self._snapshot_sort_key, reverse=True)
        for path in older[self.snapshot_keep - 1:]:
            shutil.rmtree(path)

    def _snapshot_sort_key(self, path: Path) -> tuple[bool, float]:
        timestamp = self._snapshot_timestamp(path)
        return (timestamp is not None,
                timestamp.timestamp() if timestamp is not None else path.stat().st_mtime)

    @staticmethod
    def _snapshot_timestamp(path: Path) -> datetime | None:
        """Trust freshness/retention only for complete, unaltered managed snapshots."""
        names = {"sancionados.csv", "inhabilitaciones_judiciales.csv"}
        try:
            if path.is_symlink() or not path.is_dir():
                return None
            children = list(path.iterdir())
            if {p.name for p in children} != names | {"manifest.json"}:
                return None
            if any(p.is_symlink() or not p.is_file() for p in children):
                return None
            meta = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            timestamp = datetime.fromisoformat(meta["downloaded_at"])
            if timestamp.tzinfo is None or timestamp > datetime.now(UTC):
                return None
            if set(meta["files"]) != names:
                return None
            for name in names:
                content = (path / name).read_bytes()
                info = meta["files"][name]
                if (info["bytes"] != len(content)
                        or info["sha256"] != hashlib.sha256(content).hexdigest()):
                    return None
            return timestamp.astimezone(UTC)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    @staticmethod
    def _api_url(base: str, link: object) -> str:
        if not isinstance(link, str) or not link:
            raise ValueError("Invalid OSCE link")
        url = link if link.startswith("https://") else f"{base}/{link.lstrip('/')}"
        if not url.startswith(f"{base}/"):
            raise ValueError("OSCE link is outside the configured API")
        return url

    def _extract_from_local_files(self) -> None:
        raw_dir_candidates = [
            Path(self.data_dir) / "raw" / "pe" / "osce_sanctions",
            Path(self.data_dir) / "pe" / "osce_sanctions",
            Path(self.data_dir) / "osce_sanctions",
        ]
        for raw_dir in raw_dir_candidates:
            if raw_dir.is_dir():
                self.raw_files = sorted(
                    path for path in raw_dir.iterdir()
                    if path.is_file() and path.suffix.lower() == ".csv"
                )
                if self.source_mode == "api" and not self._complete_fallback(self.raw_files):
                    self.raw_files = []
                if self.raw_files:
                    return
        snapshots = Path(self.data_dir).glob("raw/pe/osce_sanctions/api/snapshot-*")
        snapshots = (path for path in snapshots if not path.is_symlink())
        for snapshot in sorted(snapshots, key=self._snapshot_sort_key, reverse=True):
            files = [snapshot / name for name in (
                "inhabilitaciones_judiciales.csv", "sancionados.csv",
            )]
            if snapshot.is_symlink() or any(path.is_symlink() for path in files):
                continue
            manifest = snapshot / "manifest.json"
            if (manifest.exists() or manifest.is_symlink()) and self._snapshot_timestamp(
                snapshot,
            ) is None:
                continue
            if (all(path.is_file() for path in files)
                    and (self.source_mode != "api" or self._complete_fallback(files))):
                self.raw_files = files
                return
        logger.warning("[%s] no local sanction CSVs found", self.name)

    def _complete_fallback(self, files: list[Path]) -> bool:
        required = {"sancionados.csv", "inhabilitaciones_judiciales.csv"}
        if not required.issubset({p.name for p in files}):
            return False
        try:
            return all(not self._read_raw_csv(p).empty for p in files if p.name in required)
        except (OSError, ValueError):
            return False

    def transform(self) -> None:
        if self.raw_files:
            self._transform_raw_files()
            return

        providers: list[dict[str, Any]] = []
        sanctions: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []

        for idx, row in self._raw_sanctions.iterrows():
            raw_row = {str(key): value for key, value in row.to_dict().items()}
            provider, sanction, relationship = self._normalize_sanction_row(raw_row, idx)
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
            df = self._read_raw_csv(file_path)
            rows_in += len(df)
            sanctions_before_file = len(sanctions)
            for idx, row in df.iterrows():
                raw_row = {str(key): value for key, value in row.to_dict().items()}
                provider, sanction, relationship = self._normalize_sanction_row(
                    raw_row,
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
            if not df.empty and len(sanctions) == sanctions_before_file:
                msg = (
                    f"{file_path}: no valid sanction rows; expected an 11-digit RUC "
                    "and a non-empty sanction resolution"
                )
                raise ValueError(msg)
            if self.limit is not None and len(sanctions) >= self.limit:
                break

        self.rows_in = rows_in
        self.providers = deduplicate_rows(providers, ["ruc"])
        self.sanctions = deduplicate_rows(sanctions, ["sanction_id"])
        self.provider_sanctions = (
            relationships[: self.limit] if self.limit is not None else relationships
        )
        self.rows_loaded = len(self.sanctions)

        with self.normalized_csv_path.open("w", encoding="utf-8", newline="") as f:
            fieldnames = [
                "sanction_id",
                "resolution_number",
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
                        "resolution_number": sanction.get("resolution_number", ""),
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
        _idx: object,
        *,
        source_kind: str | None = None,
        source_file: str = "",
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
        doc = strip_document(self._first_value(raw_row, *_DOCUMENT_COLUMNS))
        if len(doc) != 11:
            return None, None, None

        provider_name = normalize_name(
            self._first_value(
                raw_row,
                "provider_name",
                "NOMBRE_RAZONODENOMINACIONSOCIAL",
                "RazonSocial/Nombre",
            ),
        ) or f"RUC {doc}"

        extraction_date = self._parse_extraction_date(
            self._first_value(raw_row, "extraction_date", "FECHA_CORTE"),
        )

        kind = source_kind or "tcp_vigente"
        sanction_source = "OSCE_TCP" if kind == "tcp_vigente" else "PODER_JUDICIAL"
        sanction_scope = "vigente"
        sanction_type = "INHABILITACION"
        sanction_reason = ""

        if kind == "tcp_vigente":
            sanction_type = "TRIBUNAL_CONTRATACIONES"
            sanction_reason = self._first_value(raw_row, "DE_MOTIVO_INFRACCION")
        elif kind == "judicial":
            sanction_type = "MANDATO_JUDICIAL"
            sanction_reason = self._first_value(
                raw_row,
                "ORGANO_JURISDICCIONAL",
                "OrganoJurisdiccional",
            )

        sanction_type = self._first_value(raw_row, "sanction_type") or sanction_type
        sanction_reason = self._first_value(raw_row, "sanction_reason") or sanction_reason
        resolution = self._first_value(raw_row, *_RESOLUTION_COLUMNS)
        if not resolution:
            return None, None, None
        # Encode components unambiguously; mutable provenance is not part of identity.
        identity = json.dumps(
            [self.source_id, sanction_source, sanction_type, doc, resolution],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        sanction_id = f"{self.source_id}:v1:{digest}"
        source_url = self._first_value(raw_row, "source_url") or _registry_source_url(
            self.source_id,
        )

        provider = {
            "ruc": doc,
            "legal_name": provider_name,
            "name": provider_name,
            "trade_name": "",
            "source": "osce_sanctions",
            "source_url": source_url,
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
            "date_start": self._parse_extraction_date(
                self._first_value(
                    raw_row,
                    "start_date",
                    "FECHA_INICIO",
                    "FechaInicioInhabilitacion",
                ),
            ),
            "date_end": self._parse_extraction_date(
                self._first_value(
                    raw_row,
                    "end_date",
                    "FECHA_FIN",
                    "FechaFinInhabilitacion",
                ),
            )
            or None,
            "resolution_number": resolution,
            "source": "osce_sanctions",
            "source_dataset": source_file,
            "source_url": source_url,
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
    def _read_raw_csv(file_path: Path) -> pd.DataFrame:
        try:
            with file_path.open(encoding="latin-1", newline="") as raw_file:
                header = raw_file.readline().lstrip("\ufeff").strip()
        except OSError as exc:
            msg = f"Unable to read OSCE sanctions CSV {file_path}: {exc}"
            raise ValueError(msg) from exc

        delimiter_counts = {
            delimiter: header.count(delimiter) for delimiter in _SUPPORTED_DELIMITERS
        }
        delimiter = max(delimiter_counts, key=delimiter_counts.__getitem__) if header else ""
        if not delimiter or delimiter_counts[delimiter] == 0:
            expected = " or ".join(repr(item) for item in _SUPPORTED_DELIMITERS)
            msg = f"{file_path}: unsupported CSV delimiter; expected {expected}"
            raise ValueError(msg)

        try:
            dataframe = pd.read_csv(
                file_path,
                dtype=str,
                keep_default_na=False,
                encoding="latin-1",
                sep=delimiter,
            )
        except (pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
            msg = f"{file_path}: invalid OSCE sanctions CSV: {exc}"
            raise ValueError(msg) from exc

        dataframe.columns = [str(column).lstrip("\ufeff").strip() for column in dataframe.columns]
        columns = set(dataframe.columns)
        missing_groups = []
        if not columns.intersection(_DOCUMENT_COLUMNS):
            missing_groups.append("RUC (ruc/RUC/RUC_DNI/RUC/DNI)")
        if not columns.intersection(_RESOLUTION_COLUMNS):
            missing_groups.append(
                "resolution (resolution_number/sanction_id/NUMERO_RESOLUCION/NumeroResolucion)",
            )
        if missing_groups:
            msg = f"{file_path}: missing required OSCE columns: {', '.join(missing_groups)}"
            raise ValueError(msg)
        return dataframe

    @staticmethod
    def _first_value(row: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return ""

    @staticmethod
    def _parse_extraction_date(value: str) -> str:
        value = value.strip()
        if len(value) == 8 and value.isdigit():
            return parse_date(value)
        return parse_date(value)
