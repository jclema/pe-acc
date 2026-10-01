import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import "@/i18n";

import { EdgeDetail } from "./EdgeDetail";

const rnp = {
  type: "MIEMBRO_ORGANO_DE",
  source: { id: "source-1", label: "ENTIDAD SINTÉTICA B" },
  target: { id: "target-1", label: "PROVEEDOR SINTÉTICO A" },
  properties: {
    declared_name: "ENTIDAD SINTÉTICA B", cargo: "DIRECTOR",
    source_dataset: "organos.csv", file_sha256: "a".repeat(64),
    source_url: "https://osce-gob-pe.atlassian.net/wiki/spaces/PNDA/pages/106889267",
  },
};

describe("EdgeDetail RNP", () => {
  it("shows the declaration, named endpoints and verifiable provenance without scoring it", () => {
    render(<EdgeDetail edge={rnp} onClose={vi.fn()} />);
    expect(screen.getByRole("heading")).toHaveTextContent("Miembro de órgano de administración de");
    expect(screen.getByText("PROVEEDOR SINTÉTICO A")).toBeInTheDocument();
    expect(screen.getByText("DIRECTOR")).toBeInTheDocument();
    expect(screen.getByText("organos.csv")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Abrir fuente oficial" });
    expect(link).toHaveAttribute("href", rnp.properties.source_url);
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveAttribute("target", "_blank");
    const summary = screen.getByText("Huella del archivo (SHA-256)");
    expect(summary.closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText(rnp.properties.file_sha256)).toBeInTheDocument();
    expect(screen.getByText(/Vínculo declarado en RNP/)).toBeInTheDocument();
    expect(screen.queryByText("Confianza")).not.toBeInTheDocument();
    expect(screen.queryByText("Sin valor monetario")).not.toBeInTheDocument();
  });

  it.each(["javascript:alert(1)", "data:text/html,unsafe", "not a URL", ""])(
    "does not link an unsafe or missing source (%s)", (source_url) => {
      render(<EdgeDetail edge={{ ...rnp, properties: { ...rnp.properties, source_url } }} onClose={vi.fn()} />);
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
      expect(screen.getByText("organos.csv")).toBeInTheDocument();
    },
  );

  it("omits empty role and supports string endpoint IDs", () => {
    render(<EdgeDetail edge={{ ...rnp, type: "SOCIO_DE", source: "p1", target: "p2",
      properties: { ...rnp.properties, cargo: " " } }} onClose={vi.fn()} />);
    expect(screen.getByRole("heading")).toHaveTextContent("Socio de");
    expect(screen.queryByText("Cargo declarado")).not.toBeInTheDocument();
    expect(screen.getByText("p1")).toBeInTheDocument();
  });

  it("preserves existing edge details and closes the panel", () => {
    const onClose = vi.fn();
    render(<EdgeDetail edge={{ type: "HAS_SANCTION", source: "p1", target: "s1", properties: {} }} onClose={onClose} />);
    expect(screen.getByText("Confianza")).toBeInTheDocument();
    expect(screen.queryByText(/Vínculo declarado en RNP/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button"));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
