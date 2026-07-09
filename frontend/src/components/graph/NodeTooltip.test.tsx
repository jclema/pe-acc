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
    reason: "Presentacion de informacion falsa",
    resolution_number: "OSCE-001",
    status: "VIGENTE",
    sanction_source: "OSCE_TCP",
    date_start: "2026-03-15",
    date_end: "2026-09-15",
  },
};

describe("NodeTooltip", () => {
  it("renders the source label as plain text when source_url is missing", () => {
    render(<NodeTooltip node={baseSanctionNode} x={0} y={0} />);

    expect(screen.getByText(/OSCE - Tribunal de Contrataciones/)).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("renders a clickable source link when the sanction has a source_url", () => {
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

    const link = screen.getByRole("link", { name: /OSCE - Tribunal de Contrataciones/ });
    expect(link).toHaveAttribute("href", sourceUrl);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });
});
