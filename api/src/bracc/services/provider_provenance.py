"""Project selected Provider attribution without publishing observation history."""
import json
from datetime import date
from typing import Any, Literal
from urllib.parse import urlsplit

from bracc.models.entity import ProviderFieldSource, ProviderProvenance

FIELDS = ("legal_name", "name", "trade_name", "tax_status", "tax_condition", "provider_type",
          "ubigeo", "department", "province", "district")
SOURCES = {"sunat_ruc", "pe_sunat_ruc", "osce_sanctions", "pe_osce_sanctions"}
OFFICIAL_HOSTS = ("sunat.gob.pe", "osce.gob.pe", "oece.gob.pe", "gob.pe")


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _official_url(value: Any) -> str | None:
    text = _text(value)
    if not text or any(char.isspace() or ord(char) < 32 for char in text):
        return None
    try:
        url = urlsplit(text)
        host = url.hostname or ""
        if host == "example.gob.pe" or host.endswith(".example.gob.pe"):
            return None
        if (url.scheme == "https" and not url.username and not url.password
                and url.port in (None, 443)
                and (host == "osce-gob-pe.atlassian.net"
                     or any(host == h or host.endswith("." + h) for h in OFFICIAL_HOSTS))):
            return text
    except ValueError:
        pass
    return None


def project_provider_provenance(props: dict[str, Any]) -> ProviderProvenance:
    raw = props.get("provider_field_sources")
    status: Literal["structured", "legacy", "invalid"] = "legacy"
    selected: dict[str, Any] = {}
    if raw is not None and raw != "":
        status = "invalid"
        if isinstance(raw, str):
            try:
                decoded = json.loads(raw)
                if isinstance(decoded, dict):
                    selected = decoded
                    status = "structured"
            except (ValueError, RecursionError):
                pass
    fields = {}
    for field in FIELDS:
        if not _text(props.get(field)):
            continue
        meta = selected.get(field)
        item = ProviderFieldSource()
        if isinstance(meta, dict) and _text(meta.get("source")) in SOURCES:
            item.source = _text(meta.get("source"))
            item.source_url = _official_url(meta.get("source_url"))
            dataset = _text(meta.get("source_dataset"))
            item.source_dataset = dataset.replace("\\", "/").rsplit("/", 1)[-1] if dataset else None
            cutoff = _text(meta.get("extraction_date"))
            if cutoff:
                try:
                    parsed = date.fromisoformat(cutoff).isoformat()
                    item.extraction_date = parsed if parsed == cutoff else None
                except ValueError:
                    pass
        fields[field] = item
    return ProviderProvenance(status=status, fields=fields)
