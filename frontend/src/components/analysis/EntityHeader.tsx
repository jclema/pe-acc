import { memo } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Plus } from "lucide-react";

import type { EntityDetail, ExposureResponse } from "@/api/client";
import { entityColors } from "@/styles/tokens";

import { ScoreRing } from "./ScoreRing";
import styles from "./EntityHeader.module.css";

interface EntityHeaderProps {
  entity: EntityDetail;
  exposure: ExposureResponse | null;
  onBack: () => void;
  onAddToInvestigation?: () => void;
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat("es-PE", {
    style: "currency",
    currency: "PEN",
    notation: "compact",
  }).format(value);
}

function EntityHeaderInner({
  entity,
  exposure,
  onBack,
  onAddToInvestigation,
}: EntityHeaderProps) {
  const { t } = useTranslation();

  const rawName =
    entity.properties.legal_name ??
    entity.properties.trade_name ??
    entity.properties.nome ??
    entity.properties.razao_social ??
    entity.properties.name ??
    entity.properties.title ??
    entity.properties.entity_name ??
    entity.properties.ruc ??
    entity.id;
  const name = typeof rawName === "string" ? rawName : String(rawName);
  const secondaryIdRaw =
    entity.properties.ruc ??
    entity.properties.entity_id ??
    entity.properties.process_id ??
    entity.properties.seace_code ??
    entity.properties.award_id ??
    entity.properties.execution_id ??
    entity.properties.cnpj ??
    entity.properties.cpf;
  const secondaryId = secondaryIdRaw ? String(secondaryIdRaw) : null;

  const typeColor = entityColors[entity.type] ?? "var(--text-muted)";

  const connectionCount = exposure?.factors.find((f) => f.name === "connections")?.value;
  const sourceCount = exposure?.factors.find((f) => f.name === "sources")?.value ?? entity.sources.length;
  const totalMoney = exposure?.factors.find((f) => f.name === "financial");

  return (
    <header className={styles.header}>
      <button
        className={styles.backBtn}
        onClick={onBack}
        aria-label={t("common.back")}
      >
        <ArrowLeft size={16} />
      </button>

      <div className={styles.identity}>
        <span className={styles.name}>{name}</span>
        {secondaryId && <span className={styles.secondaryId}>{secondaryId}</span>}
      </div>

      <span className={styles.typeBadge}>
        <span
          className={styles.typeDot}
          style={{ backgroundColor: typeColor }}
        />
        {t(`entity.${entity.type}`, entity.type)}
      </span>

      {exposure && (
        <ScoreRing value={exposure.exposure_index} size={40} />
      )}

      <div className={styles.sourceBadges}>
        {entity.sources.map((s) => (
          <span key={s.database} className={styles.sourcePill}>
            {s.database}
          </span>
        ))}
      </div>

      <div className={styles.stats}>
        {connectionCount != null && (
          <span className={styles.stat}>
            {connectionCount} {t("common.connections")}
          </span>
        )}
        <span className={styles.stat}>
          {sourceCount} {t("common.sources")}
        </span>
        {totalMoney && (
          <span className={styles.stat}>{formatMoney(totalMoney.value)}</span>
        )}
      </div>

      {onAddToInvestigation && (
        <button className={styles.addBtn} onClick={onAddToInvestigation}>
          <Plus size={14} />
          {t("investigation.addEntity")}
        </button>
      )}
    </header>
  );
}

export const EntityHeader = memo(EntityHeaderInner);
