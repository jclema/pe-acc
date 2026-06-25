import { useState } from "react";
import { useTranslation } from "react-i18next";

import styles from "./SearchBar.module.css";

export interface SearchParams {
  query: string;
  type: string;
}

interface SearchBarProps {
  onSearch: (params: SearchParams) => void;
  isLoading?: boolean;
}

export function SearchBar({ onSearch, isLoading }: SearchBarProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [type, setType] = useState("all");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    onSearch({ query: trimmed, type });
  };

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <input
        type="text"
        className={styles.input}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t("search.placeholder")}
        aria-label={t("search.placeholder")}
      />
      <select
        className={styles.select}
        value={type}
        onChange={(e) => setType(e.target.value)}
        aria-label={t("search.filterType")}
      >
        <option value="all">{t("search.typeAll")}</option>
        <option value="provider">{t("entity.provider")}</option>
        <option value="company">{t("entity.company")}</option>
        <option value="entity">{t("entity.entity")}</option>
        <option value="procurementprocess">{t("entity.procurementprocess")}</option>
        <option value="award">{t("entity.award")}</option>
        <option value="sanction">{t("entity.sanction")}</option>
      </select>
      <button type="submit" className={styles.button} disabled={isLoading}>
        {isLoading ? t("common.loading") : t("search.button")}
      </button>
    </form>
  );
}
