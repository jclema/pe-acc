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
  it("links the provider source inside the existing node card", () => {
    render(<NodeTooltip node={{ id: "p1", label: "PROVEEDOR DE PRUEBA", type: "provider",
      connectionCount: 1, document_id: "20990000001",
      properties: { source_url: "https://osce-gob-pe.atlassian.net/wiki/pages/viewpage.action?pageId=106889269" },
      sources: [{ database: "osce_sanctions" }],
    }} x={0} y={0} />);
    expect(screen.getByText("20990000001")).toBeVisible();
    expect(screen.getByRole("link", { name: "Abrir fuente: OSCE - Proveedores sancionados" }))
      .toHaveAttribute("href", "https://osce-gob-pe.atlassian.net/wiki/pages/viewpage.action?pageId=106889269");
  });

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


it.each(["https://example.gob.pe/osce/001", "https://EXAMPLE.GOB.PE/osce/001",
  "https://sub.example.gob.pe/osce/001", "https://example.org/source"])(
  "labels demo sources without publishing a broken link (%s)", (source_url) => {
    render(<NodeTooltip node={{ ...baseSanctionNode,
      properties: { ...baseSanctionNode.properties, source_url } }} x={0} y={0} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("Datos de demostración; sin enlace verificable.")).toBeVisible();
  },
);
