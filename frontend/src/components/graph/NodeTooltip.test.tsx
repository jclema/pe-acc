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
