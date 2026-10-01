import { useTranslation } from "react-i18next";

import { MoneyLabel } from "@/components/common/MoneyLabel";

import styles from "./EdgeDetail.module.css";

interface EdgeDetailProps {
  edge: {
    type: string;
    source?: string | number | { id?: string | number; [k: string]: unknown };
    target?: string | number | { id?: string | number; [k: string]: unknown };
    value?: number;
    confidence?: number;
    properties: Record<string, unknown>;
  };
  onClose: () => void;
}

function resolveId(ref: string | number | { id?: string | number; [k: string]: unknown } | undefined): string {
  if (ref == null) return "";
  if (typeof ref === "string") return ref;
  if (typeof ref === "number") return String(ref);
  return String(ref.id ?? "");
}

function safeSourceUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value.trim());
    return ["https:", "http:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function resolveLabel(ref: EdgeDetailProps["edge"]["source"]): string {
  return ref && typeof ref === "object" && typeof ref.label === "string"
    ? ref.label : resolveId(ref);
}

export function EdgeDetail({ edge, onClose }: EdgeDetailProps) {
  const { t } = useTranslation();

  const sourceId = resolveId(edge.source);
  const targetId = resolveId(edge.target);
  const props = edge.properties;
  const isRnp = ["SOCIO_DE", "REPRESENTA_A", "MIEMBRO_ORGANO_DE"].includes(edge.type)
    && typeof props.source_dataset === "string" && typeof props.file_sha256 === "string";
  const sourceUrl = safeSourceUrl(props.source_url);
  const rnpFields = ["declared_name", "cargo", "source_dataset"] as const;
  const databases = edge.properties.database
    ? [String(edge.properties.database)]
    : edge.properties.databases
      ? (edge.properties.databases as string[])
      : [];

  return (
    <div className={styles.panel}>
      <button className={styles.close} onClick={onClose} aria-label="Close">
        &times;
      </button>

      <h3 className={styles.type}>{t(`relationship.${edge.type}`, edge.type)}</h3>

      <dl className={styles.fields}>
        <dt>{t("graph.edge.source")}</dt>
        <dd className={styles.mono}>{isRnp ? resolveLabel(edge.source) : sourceId}</dd>

        <dt>{t("graph.edge.target")}</dt>
        <dd className={styles.mono}>{isRnp ? resolveLabel(edge.target) : targetId}</dd>

        {!isRnp && <>
        <dt>{t("graph.edge.value")}</dt>
        <dd>
          {edge.value != null && edge.value > 0 ? (
            <MoneyLabel value={edge.value} />
          ) : (
            <span className={styles.muted}>{t("graph.edge.noValue")}</span>
          )}
        </dd>

        <dt>{t("graph.edge.confidence")}</dt>
        <dd>{Math.round((edge.confidence ?? 1) * 100)}%</dd>
        </>}

        {isRnp && <>
          {rnpFields.map((key) => typeof props[key] === "string" && props[key].trim() && (
            <div className={styles.field} key={key}>
              <dt>{t(`graph.edge.${key}`)}</dt>
              <dd>{String(props[key])}</dd>
            </div>
          ))}
          {sourceUrl && <>
            <dt>{t("graph.edge.sources")}</dt>
            <dd><a className={styles.sourceLink} href={sourceUrl} target="_blank"
              rel="noopener noreferrer">{t("graph.edge.openSource")}</a></dd>
          </>}
        </>}

        {databases.length > 0 && (
          <>
            <dt>{t("graph.edge.sources")}</dt>
            <dd>{databases.join(", ")}</dd>
          </>
        )}
      </dl>
      {isRnp && <>
        <p className={styles.notice}>{t("graph.edge.rnpNotice")}</p>
        <details className={styles.fingerprint}>
          <summary>{t("graph.edge.fileHash")}</summary>
          <code>{String(props.file_sha256)}</code>
        </details>
      </>}
    </div>
  );
}
