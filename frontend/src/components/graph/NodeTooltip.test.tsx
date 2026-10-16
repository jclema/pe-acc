import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import "@/i18n";

import { NodeTooltip } from "./NodeTooltip";

const baseSanctionNode = {
  id: "sanction-1",
  label: "TRIBUNAL_CONTRATACIONES",
  type: "sanction",
  connectionCount: 1,
  properties: {
    type: "TRIBUNAL_CONTRATACIONES",
    reason: "Registro publicado por la fuente",
    resolution_number: "OSCE-001",
    status: "VIGENTE",
    sanction_source: "OSCE_TCP",
  },
};

describe("NodeTooltip", () => {
  it("keeps the business identifier when the source title is empty", () => {
    render(<NodeTooltip x={0} y={0} node={{ id: "a", type: "award", label: "SEACE-101",
      connectionCount: 1, properties: { award_title: "" } }} />);
    expect(screen.getByText("SEACE-101")).toBeInTheDocument();
  });

  it.each(["https://example.test/awards.xlsx#row=2", "javascript:alert(1)"])(
    "shows award evidence and only safe source links (%s)", (source_url) => {
      render(<NodeTooltip x={0} y={0} node={{
        id: "award-1", type: "award", label: "EQUIPOS FICTICIOS", connectionCount: 2,
        properties: { amount: 100, currency: "PEN", award_date: "2026-06-02",
          award_title: "TITULO COMPLETO DE LA ADJUDICACION",
          source_dataset: "awards.xlsx", source_row: "2", file_sha256: "a".repeat(64),
          source_url },
      }} />);
      expect(screen.getByText("2026-06-02")).toBeInTheDocument();
      expect(screen.getByText("TITULO COMPLETO DE LA ADJUDICACION")).toBeInTheDocument();
      expect(screen.getByText("awards.xlsx")).toBeInTheDocument();
      expect(screen.getByText(/100[.,]00/)).toBeInTheDocument();
      expect(screen.getByText("a".repeat(64))).toBeInTheDocument();
      if (source_url.startsWith("https:")) {
        expect(screen.getByRole("link")).toHaveAttribute("href", source_url);
      } else expect(screen.queryByRole("link")).not.toBeInTheDocument();
    },
  );

  it("renders the source as accessible external link for an HTTPS URL", () => {
    const sourceUrl = "https://www.datosabiertos.gob.pe/dataset/proveedores-sancionados";
    render(
      <NodeTooltip
        node={{
          ...baseSanctionNode,
          properties: { ...baseSanctionNode.properties, source_url: sourceUrl },
        }}
        x={0}
        y={0}
      />,
    );

    const link = screen.getByRole("link", { name: /abrir fuente/i });
    expect(link).toHaveAttribute("href", sourceUrl);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it.each([undefined, "javascript:alert(1)", "not a URL"])(
    "renders plain source text when source_url is absent or unsafe (%s)",
    (sourceUrl) => {
      render(
        <NodeTooltip
          node={{
            ...baseSanctionNode,
            properties: { ...baseSanctionNode.properties, source_url: sourceUrl },
          }}
          x={0}
          y={0}
        />,
      );

      expect(screen.getByText(/OSCE - Tribunal de Contrataciones/)).toBeInTheDocument();
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
    },
  );
});
