import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { EntityDetail } from "@/api/client";
import { ProviderProvenance } from "./ProviderProvenance";

const entity: EntityDetail = {
  id: "20123456789", type: "provider", is_pep: false,
  properties: { legal_name: "DEMO", name: "DEMO", tax_status: "ACTIVO" },
  sources: [{ database: "sunat_ruc" }],
  provider_provenance: { status: "structured", fields: {
    legal_name: { source: "sunat_ruc", source_url: "https://www.sunat.gob.pe/",
      source_dataset: "padron.csv", extraction_date: "2026-09-01" },
    tax_status: { source: "osce_sanctions", source_url: null,
      source_dataset: null, extraction_date: null },
  } },
};

async function open(data = entity) {
  render(<ProviderProvenance entity={data} />);
  await userEvent.setup().click(screen.getByText("Procedencia por campo"));
}

describe("ProviderProvenance", () => {
  it("shows different sources by field and explicit unknown metadata", async () => {
    await open();
    const fields = screen.getAllByRole("listitem");
    expect(fields).toHaveLength(2);
    expect(within(fields[0]!).getByRole("heading", { name: "Razón social" })).toBeVisible();
    expect(within(fields[0]!).getByText("SUNAT — Padrón RUC")).toBeVisible();
    const link = within(fields[0]!).getByRole("link", { name: "Fuente oficial de Razón social" });
    expect(link).toHaveAttribute("href", "https://www.sunat.gob.pe/");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(fields[0]!).getByText("padron.csv")).toBeVisible();
    expect(within(fields[0]!).getByText("2026-09-01")).toHaveAttribute("datetime", "2026-09-01");
    expect(within(fields[1]!).getByText("OSCE — Sanciones")).toBeVisible();
    expect(within(fields[1]!).getAllByText("Desconocido")).toHaveLength(2);
  });

  it.each([undefined, null, { status: "legacy", fields: {} }, { status: "invalid", fields: {} }] as const)(
    "does not infer attribution from legacy source badges or download date (%j)", async (provenance) => {
      await open({ ...entity, provider_provenance: provenance,
        properties: { legal_name: "DEMO", extraction_date: "2026-10-14" } });
      expect(screen.getByText("Atribución por campo desconocida para este proveedor.")).toBeVisible();
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
      expect(screen.queryByText("2026-10-14")).not.toBeInTheDocument();
      expect(screen.getAllByText("Desconocido")).toHaveLength(3);
    },
  );

  it.each(["javascript:alert(1)", "https://evil.com/", "http://sunat.gob.pe/",
    "https://sunat.gob.pe.evil.com/", "https://user:pass@sunat.gob.pe/",
    "https://sunat.gob.pe:444/", "https://sunat.gob.pe/\nsecret"])(
    "rejects unsafe links: %s", async (url) => {
      await open({ ...entity, provider_provenance: { status: "structured", fields: {
        legal_name: { source: "sunat_ruc", source_url: url,
          source_dataset: null, extraction_date: null },
      } } });
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
    },
  );

  it("handles a provider with no selected fields and hides arbitrary fields", async () => {
    await open({ ...entity, properties: { ruc: entity.id, operator_note: "PRIVATE" } });
    expect(screen.getByText("No hay campos con procedencia disponible.")).toBeVisible();
    expect(screen.queryByText("PRIVATE")).not.toBeInTheDocument();
  });

  it("uses a focusable native disclosure and omits non-provider entities", async () => {
    const { rerender } = render(<ProviderProvenance entity={entity} />);
    const user = userEvent.setup();
    screen.getByText("Procedencia por campo").focus();
    expect(screen.getByText("Procedencia por campo")).toHaveFocus();
    await user.click(screen.getByText("Procedencia por campo"));
    expect(screen.getByRole("link")).toBeVisible();
    rerender(<ProviderProvenance entity={{ ...entity, type: "company" }} />);
    expect(screen.queryByText("Procedencia por campo")).not.toBeInTheDocument();
  });
});

it.each(["unregistered", "constructor", "__proto__"])("keeps unknown source %s unlinked", async (source) => {
  await open({ ...entity, provider_provenance: { status: "structured", fields: {
    legal_name: { source, source_url: "https://sunat.gob.pe/", source_dataset: "private.csv",
      extraction_date: "2026-10-14" },
  } } });
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  expect(screen.queryByText("private.csv")).not.toBeInTheDocument();
});

it.each(["2026-02-31", "2026-99-01", "downloaded today"])("does not present invalid cutoff %s", async (date) => {
  await open({ ...entity, provider_provenance: { status: "structured", fields: {
    legal_name: { source: "sunat_ruc", source_url: null, source_dataset: null,
      extraction_date: date },
  } } });
  expect(screen.queryByText(date)).not.toBeInTheDocument();
});


it("labels demo provider metadata without inferring a real official source", async () => {
  await open({ ...entity, properties: { legal_name: "DEMO",
    source_url: "https://example.gob.pe/osce/001" },
    provider_provenance: { status: "structured", fields: { legal_name: {
      source: "sunat_ruc", source_url: "https://example.gob.pe/sunat/20123456789",
      source_dataset: "demo.csv", extraction_date: "2026-04-01" } } } });
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  expect(screen.getByText("Incluye datos de demostración; los enlaces de ejemplo no son verificables.")).toBeVisible();
  expect(screen.getByText("demo.csv")).toBeVisible();
});

it("identifies a legacy demo URL without attributing its fields", async () => {
  await open({ ...entity, properties: { legal_name: "DEMO",
    source_url: "https://example.gob.pe/osce/001" }, provider_provenance: null });
  expect(screen.getByText("Incluye datos de demostración; los enlaces de ejemplo no son verificables.")).toBeVisible();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  expect(screen.getAllByText("Desconocido")).toHaveLength(3);
});


it("keeps a real field source linked when another field has a demo URL", async () => {
  await open({ ...entity, provider_provenance: { status: "structured", fields: {
    legal_name: { source: "sunat_ruc", source_url: "https://example.gob.pe/sunat",
      source_dataset: "demo.csv", extraction_date: null },
    tax_status: { source: "osce_sanctions", source_url: "https://www.gob.pe/osce",
      source_dataset: "osce.csv", extraction_date: null },
  } } });
  expect(screen.getByText("Incluye datos de demostración; los enlaces de ejemplo no son verificables.")).toBeVisible();
  expect(screen.getAllByRole("link")).toHaveLength(1);
  expect(screen.getByRole("link", { name: "Fuente oficial de Estado tributario" })).toHaveAttribute("href", "https://www.gob.pe/osce");
});
