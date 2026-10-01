import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import "@/i18n";

import { ControlsSidebar } from "./ControlsSidebar";

it("labels RNP filters in Spanish and toggles the relationship identifier", () => {
  const onToggleRelType = vi.fn();
  render(<ControlsSidebar collapsed={false} onToggle={vi.fn()} depth={2}
    onDepthChange={vi.fn()} enabledTypes={new Set()} onToggleType={vi.fn()}
    enabledRelTypes={new Set(["SOCIO_DE", "REPRESENTA_A", "MIEMBRO_ORGANO_DE"])}
    onToggleRelType={onToggleRelType} typeCounts={{}} relTypeCounts={{ REPRESENTA_A: 1 }} />);
  expect(screen.getByRole("button", { name: "Socio de 0" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Miembro de órgano de administración de 0" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Representa a 1" }));
  expect(onToggleRelType).toHaveBeenCalledWith("REPRESENTA_A");
});
