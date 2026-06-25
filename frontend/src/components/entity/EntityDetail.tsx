import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { type EntityDetail as EntityDetailData, getEntity, getEntityByElementId } from "@/api/client";
import { SourceBadge } from "@/components/common/SourceBadge";
import { type EntityType, entityColors } from "@/styles/tokens";

import styles from "./EntityDetail.module.css";

interface EntityDetailProps {
  entityId: string | null;
  onClose: () => void;
}

export function EntityDetail({ entityId, onClose }: EntityDetailProps) {
  const { t } = useTranslation();
  const [entity, setEntity] = useState<EntityDetailData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!entityId) {
      setEntity(null);
      return;
    }
    setLoading(true);
    const isPublicIdentifier = /^\d{11}$/.test(entityId) || /^\d{14}$/.test(entityId);
    const fetcher = isPublicIdentifier ? getEntity(entityId) : getEntityByElementId(entityId);
    fetcher
      .then(setEntity)
      .catch(() => setEntity(null))
      .finally(() => setLoading(false));
  }, [entityId]);

  if (!entityId) return null;

  const identityPairs = entity
    ? [
      ["RUC", entity.properties.ruc],
      ["Entidad", entity.properties.entity_id],
      ["Proceso", entity.properties.process_id],
      ["Codigo SEACE", entity.properties.seace_code],
      ["Adjudicacion", entity.properties.award_id],
      ["Ejecucion", entity.properties.execution_id],
      ["CNPJ", entity.properties.cnpj],
      ["CPF", entity.properties.cpf],
    ].filter(([, value]) => value != null && value !== "")
    : [];

  const summaryPairs = entity
    ? [
      ["Estado", entity.properties.status],
      ["Estado tributario", entity.properties.tax_status],
      ["Condicion", entity.properties.tax_condition],
      ["Nivel de gobierno", entity.properties.government_level],
      ["Sector", entity.properties.sector],
      ["Metodo", entity.properties.selection_method],
      ["Fecha convocatoria", entity.properties.call_date],
      ["Fecha adjudicacion", entity.properties.award_date],
      ["Inicio sancion", entity.properties.date_start],
      ["Fin sancion", entity.properties.date_end],
      ["Ubigeo", entity.properties.ubigeo],
      ["Monto", entity.properties.amount ?? entity.properties.value],
      ["Motivo", entity.properties.reason],
      ["Fuente URL", entity.properties.source_url],
      ["Extraccion", entity.properties.extraction_date],
    ].filter(([, value]) => value != null && value !== "")
    : [];

  const otherPairs = entity
    ? Object.entries(entity.properties).filter(
      ([key]) => ![
        "name", "razao_social", "nome", "legal_name", "trade_name", "title", "entity_name",
        "cpf", "cnpj", "ruc", "entity_id", "process_id", "seace_code", "award_id", "execution_id",
        "status", "tax_status", "tax_condition", "government_level", "sector", "selection_method",
        "call_date", "award_date", "date_start", "date_end", "ubigeo", "amount", "value",
        "reason", "source_url", "extraction_date",
      ].includes(key),
    )
    : [];

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <span className={styles.title}>{t("entity.detail")}</span>
        <button onClick={onClose} className={styles.close}>
          &times;
        </button>
      </div>

      {loading && <p className={styles.loading}>{t("common.loading")}</p>}

      {entity && (
        <div className={styles.content}>
          <div
            className={styles.typeTag}
            style={{ color: entityColors[entity.type as EntityType] ?? "#555" }}
          >
            {t(`entity.${entity.type}`, entity.type)}
          </div>
          <h3 className={styles.name}>
            {String(
              entity.properties.legal_name
              ?? entity.properties.trade_name
              ?? entity.properties.name
              ?? entity.properties.razao_social
              ?? entity.properties.nome
              ?? entity.properties.title
              ?? entity.properties.entity_name
              ?? "N/A",
            )}
          </h3>

          {identityPairs.length > 0 && (
            <div className={styles.section}>
              <span className={styles.sectionTitle}>Identificadores</span>
              <div className={styles.properties}>
                {identityPairs.map(([key, value]) => (
                  <div key={`${key}-${String(value)}`} className={styles.property}>
                    <span className={styles.propKey}>{key}</span>
                    <span className={styles.propValue}>{String(value)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {summaryPairs.length > 0 && (
            <div className={styles.section}>
              <span className={styles.sectionTitle}>Resumen</span>
              <div className={styles.properties}>
                {summaryPairs.map(([key, value]) => (
                  <div key={`${key}-${String(value)}`} className={styles.property}>
                    <span className={styles.propKey}>{key}</span>
                    <span className={styles.propValue}>{String(value)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {otherPairs.length > 0 && (
            <div className={styles.section}>
              <span className={styles.sectionTitle}>Otros campos</span>
              <div className={styles.properties}>
                {otherPairs.map(([key, value]) => (
                  <div key={key} className={styles.property}>
                    <span className={styles.propKey}>{key}</span>
                    <span className={styles.propValue}>{String(value ?? "—")}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {entity.sources.length > 0 && (
            <div className={styles.sources}>
              <span className={styles.sourcesLabel}>{t("common.source")}:</span>
              {entity.sources.map((s) => (
                <SourceBadge key={s.database} source={s.database} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
