import { memo } from "react";
import { useTranslation } from "react-i18next";

import { dataColors, type DataEntityType } from "@/styles/tokens";

import styles from "./NodeTooltip.module.css";

interface TooltipNode {
  id: string;
  label: string;
  type: string;
  connectionCount: number;
  document_id?: string;
  properties?: Record<string, unknown>;
  sources?: Array<{ database: string }>;
}

interface NodeTooltipProps {
  node: TooltipNode | null;
  x: number;
  y: number;
}

function NodeTooltipInner({ node, x, y }: NodeTooltipProps) {
  const { t } = useTranslation();

  if (!node) return null;

  const color =
    dataColors[node.type as DataEntityType] ?? "#5a6b60";

  const isSanction = node.type === "sanction";
  const sanctionType = typeof node.properties?.type === "string" ? node.properties.type : null;
  const resolution = typeof node.properties?.resolution_number === "string"
    ? node.properties.resolution_number
    : typeof node.document_id === "string"
      ? node.document_id
      : null;
  const sanctionStatus = typeof node.properties?.status === "string" ? node.properties.status : null;
  const sanctionSource = typeof node.properties?.sanction_source === "string"
    ? node.properties.sanction_source
    : node.sources?.[0]?.database ?? null;
  const dateStart = typeof node.properties?.date_start === "string" ? node.properties.date_start : null;
  const dateEnd = typeof node.properties?.date_end === "string" ? node.properties.date_end : null;
  const validity = dateStart || dateEnd
    ? [dateStart, dateEnd].filter(Boolean).join(" - ")
    : sanctionStatus;

  return (
    <div
      className={styles.tooltip}
      style={{ left: x, top: y }}
    >
      <div className={styles.header}>
        <span className={styles.dot} style={{ backgroundColor: color }} />
        <span className={styles.type}>
          {t(`entity.${node.type}`, node.type)}
        </span>
      </div>
      <span className={styles.name}>{node.label}</span>
      {!isSanction && node.document_id && (
        <span className={styles.document}>{node.document_id}</span>
      )}
      {isSanction && (
        <div className={styles.summary}>
          {sanctionType && <span className={styles.meta}><strong>Tipo:</strong> {sanctionType}</span>}
          {resolution && <span className={styles.meta}><strong>Resolución:</strong> {resolution}</span>}
          {validity && <span className={styles.meta}><strong>Vigencia:</strong> {validity}</span>}
          {sanctionSource && <span className={styles.meta}><strong>Fuente:</strong> {sanctionSource}</span>}
        </div>
      )}
      <span className={styles.connections}>
        {node.connectionCount} {t("common.connections")}
      </span>
    </div>
  );
}

export const NodeTooltip = memo(NodeTooltipInner);
