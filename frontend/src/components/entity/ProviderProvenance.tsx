import type { EntityDetail } from "@/api/client";
import { isDemoSourceUrl, safeSourceUrl } from "@/lib/sourceUrl";
import styles from "./ProviderProvenance.module.css";

const fields: [string, string][] = [
  ["legal_name", "Razón social"], ["name", "Nombre"], ["trade_name", "Nombre comercial"],
  ["tax_status", "Estado tributario"], ["tax_condition", "Condición tributaria"],
  ["provider_type", "Tipo de proveedor"], ["ubigeo", "Ubigeo"],
  ["department", "Departamento"], ["province", "Provincia"], ["district", "Distrito"],
];
const sourceLabels: Record<string, string> = {
  sunat_ruc: "SUNAT — Padrón RUC", pe_sunat_ruc: "SUNAT — Padrón RUC",
  osce_sanctions: "OSCE — Sanciones", pe_osce_sanctions: "OSCE — Sanciones",
};

function officialUrl(value: string | null | undefined): string | null {
  if (!value || !safeSourceUrl(value)) return null;
  try {
    const url = new URL(value);
    if (url.protocol === "https:" && !url.username && !url.password && !url.port
      && (url.hostname === "gob.pe" || url.hostname.endsWith(".gob.pe")
        || url.hostname === "osce-gob-pe.atlassian.net")) return url.href;
  } catch { /* Unknown or malformed URL. */ }
  return null;
}

export function ProviderProvenance({ entity }: { entity: EntityDetail }) {
  if (entity.type !== "provider") return null;
  const provenance = entity.provider_provenance;
  const isDemo = isDemoSourceUrl(entity.properties.source_url)
    || Object.values(provenance?.fields ?? {}).some((field) => isDemoSourceUrl(field.source_url));
  const currentFields = fields.filter(([key]) =>
    typeof entity.properties[key] === "string" && String(entity.properties[key]).trim()
    && !(key === "name" && entity.properties.legal_name));

  return (
    <details className={styles.section}>
      <summary>Procedencia por campo</summary>
      <div className={styles.content}>
        {isDemo && <p>Incluye datos de demostración; los enlaces de ejemplo no son verificables.</p>}
        {provenance?.status !== "structured" && (
          <p>Atribución por campo desconocida para este proveedor.</p>
        )}
        {currentFields.length === 0 && <p>No hay campos con procedencia disponible.</p>}
        <ul className={styles.fields}>
          {currentFields.map(([key, label]) => {
            const candidate = provenance?.status === "structured" ? provenance.fields[key] : null;
            const meta = candidate?.source && Object.hasOwn(sourceLabels, candidate.source) ? candidate : null;
            const url = officialUrl(meta?.source_url);
            const cutoff = meta?.extraction_date;
            const date = cutoff && /^\d{4}-\d{2}-\d{2}$/.test(cutoff)
              && !Number.isNaN(Date.parse(cutoff))
              && new Date(cutoff).toISOString().slice(0, 10) === cutoff ? cutoff : null;
            return (
              <li key={key}>
                <h4>{label}</h4>
                <dl>
                  <div><dt>Fuente</dt><dd>{meta?.source ? sourceLabels[meta.source] : "Desconocido"}</dd></div>
                  <div><dt>Archivo</dt><dd>{meta?.source_dataset?.trim() || "Desconocido"}</dd></div>
                  <div><dt>Corte informado</dt><dd>{date ? <time dateTime={date}>{date}</time> : "Desconocido"}</dd></div>
                </dl>
                {url && <a href={url} target="_blank" rel="noopener noreferrer">Fuente oficial de {label}</a>}
              </li>
            );
          })}
        </ul>
      </div>
    </details>
  );
}
