import { act, fireEvent, render, screen } from "@testing-library/react";
import { useImperativeHandle, type Ref } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import i18n from "@/i18n";
import { ControlsSidebar } from "./ControlsSidebar";

import type { GraphData } from "@/api/client";
import { useGraphExplorerStore } from "@/stores/graphExplorer";

// Polyfill for jsdom
if (typeof Element.prototype.requestFullscreen === "undefined") {
  Element.prototype.requestFullscreen = vi.fn().mockResolvedValue(undefined);
}
if (typeof document.exitFullscreen === "undefined") {
  document.exitFullscreen = vi.fn().mockResolvedValue(undefined);
}

let capturedProps: Record<string, unknown> = {};
const graphMethods = vi.hoisted(() => ({
  d3Force: vi.fn(), d3ReheatSimulation: vi.fn(),
  zoomToFit: vi.fn(), pauseAnimation: vi.fn(), zoom: vi.fn(),
  graph2ScreenCoords: vi.fn(() => ({ x: 100, y: 200 })),
}));
afterEach(() => { vi.clearAllMocks(); vi.useRealTimers(); });

vi.mock("react-force-graph-2d", () => ({
  __esModule: true,
  default: vi.fn((props: Record<string, unknown>) => {
    capturedProps = props;
    useImperativeHandle(props.ref as Ref<unknown>, () => graphMethods);
    return <div data-testid="force-graph" />;
  }),
}));

import { GraphCanvas } from "./GraphCanvas";

const sampleData: GraphData = {
  nodes: [
    { id: "n1", label: "Node 1", type: "person", properties: {}, sources: [] },
    { id: "n2", label: "Node 2", type: "company", properties: {}, sources: [] },
    { id: "n3", label: "Node 3", type: "sanction", properties: {}, sources: [] },
  ],
  edges: [
    { id: "r1", source: "n1", target: "n2", type: "PARTNER", properties: {}, confidence: 1.0, sources: [] },
    { id: "r2", source: "n2", target: "n3", type: "SANCTIONED", properties: {}, confidence: 0.8, sources: [] },
  ],
};

const defaultProps = {
  data: sampleData,
  centerId: "n1",
  enabledTypes: new Set(["person", "company", "sanction"]),
  enabledRelTypes: new Set(["PARTNER", "SANCTIONED"]),
  hiddenNodeIds: new Set<string>(),
  selectedNodeIds: new Set<string>(),
  hoveredNodeId: null,
  layoutMode: "force" as const,
  onNodeClick: vi.fn(),
  onNodeDeselect: vi.fn(),
  onNodeHover: vi.fn(),
  onNodeRightClick: vi.fn(),
  onLayoutChange: vi.fn(),
  onFullscreen: vi.fn(),
  sidebarCollapsed: false,
};

describe("GraphCanvas", () => {
  it("keeps navigation enabled after layout settles and cancels pending work on unmount", () => {
    vi.useFakeTimers();
    const context = vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    const { rerender, unmount } = render(<GraphCanvas {...defaultProps} />);
    const data = capturedProps.graphData;
    act(() => {
      (capturedProps.onEngineStop as () => void)();
      vi.advanceTimersByTime(1000);
      (capturedProps.onEngineStop as () => void)();
    });
    expect(graphMethods.zoomToFit).toHaveBeenCalledOnce();
    expect(graphMethods.pauseAnimation).not.toHaveBeenCalled();
    expect(capturedProps.autoPauseRedraw).toBe(true);
    act(() => screen.getByTitle(i18n.t("graph.zoomIn")).click());
    expect(graphMethods.zoom).toHaveBeenCalledWith(1.5, 300);
    rerender(<GraphCanvas {...defaultProps} enabledRelTypes={new Set()} />);
    expect(capturedProps.graphData).toBe(data);
    expect(graphMethods.pauseAnimation).not.toHaveBeenCalled();
    rerender(<GraphCanvas {...defaultProps} data={{ ...sampleData, nodes: [...sampleData.nodes] }} />);
    act(() => (capturedProps.onEngineStop as () => void)());
    act(() => (capturedProps.onNodeHover as (node: unknown) => void)({ id: "n2" }));
    unmount();
    expect(graphMethods.pauseAnimation).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
    act(() => vi.advanceTimersByTime(1000));
    expect(graphMethods.zoomToFit).toHaveBeenCalledOnce();
    context.mockRestore();
  });

  it("shows all RNP links initially and hides only the toggled relationship", () => {
    useGraphExplorerStore.getState().reset();
    const store = useGraphExplorerStore.getState();
    const edges = ["SOCIO_DE", "REPRESENTA_A", "MIEMBRO_ORGANO_DE"].map((type) => ({
      id: type, source: "p1", target: "p2", type,
      properties: {}, confidence: 1, sources: [],
    }));
    const data: GraphData = {
      nodes: ["p1", "p2"].map((id) => ({
        id, label: id, type: "provider", properties: {}, sources: [],
      })),
      edges,
    };
    const { rerender } = render(
      <GraphCanvas {...defaultProps} data={data} centerId="p2"
        enabledTypes={store.enabledTypes} enabledRelTypes={store.enabledRelTypes} />,
    );
    const visible = () => capturedProps.linkVisibility as (edge: typeof edges[number]) => boolean;
    expect(edges.every(visible())).toBe(true);
    store.toggleRelType("REPRESENTA_A");
    rerender(
      <GraphCanvas {...defaultProps} data={data} centerId="p2"
        enabledTypes={store.enabledTypes}
        enabledRelTypes={useGraphExplorerStore.getState().enabledRelTypes} />,
    );
    expect(edges.map(visible())).toEqual([true, false, true]);
    useGraphExplorerStore.getState().reset();
  });

  it("renders ForceGraph2D component", () => {
    render(<GraphCanvas {...defaultProps} />);
    expect(screen.getByTestId("force-graph")).toBeInTheDocument();
  });

  it("passes graphData with correct nodes and links", () => {
    render(<GraphCanvas {...defaultProps} />);
    const graphData = capturedProps.graphData as { nodes: unknown[]; links: unknown[] };
    expect(graphData.nodes).toHaveLength(3);
    expect(graphData.links).toHaveLength(2);
  });

  it("uses nodeVisibility to filter by enabledTypes", () => {
    render(
      <GraphCanvas
        {...defaultProps}
        enabledTypes={new Set(["person", "company"])}
      />,
    );

    // graphData still contains all nodes (simulation stability)
    const graphData = capturedProps.graphData as { nodes: { id: string }[]; links: unknown[] };
    expect(graphData.nodes).toHaveLength(3);
    expect(graphData.links).toHaveLength(2);

    // nodeVisibility callback hides disabled types
    const nodeVis = capturedProps.nodeVisibility as (node: { id: string; type: string }) => boolean;
    expect(nodeVis({ id: "n1", type: "person" })).toBe(true);
    expect(nodeVis({ id: "n2", type: "company" })).toBe(true);
    expect(nodeVis({ id: "n3", type: "sanction" })).toBe(false);
  });

  it("invokes onNodeClick when node is clicked", () => {
    const onNodeClick = vi.fn();
    render(<GraphCanvas {...defaultProps} onNodeClick={onNodeClick} />);

    const handler = capturedProps.onNodeClick as (node: { id: string }) => void;
    act(() => handler({ id: "n2" }));
    expect(onNodeClick).toHaveBeenCalledWith("n2");
  });

  it("invokes onFullscreen when toolbar fullscreen button is clicked", () => {
    const onFullscreen = vi.fn();
    render(<GraphCanvas {...defaultProps} onFullscreen={onFullscreen} />);
    
    // The GraphToolbar's onFullscreen is connected to handleFullscreenToggle
    // We can find the button by its title from i18n
    const fullscreenBtn = screen.getByTitle(i18n.t("graph.fullscreen"));
    fullscreenBtn.click();
    
    expect(onFullscreen).toHaveBeenCalled();
  });
});

function openEdge(edge: unknown) {
  render(<GraphCanvas {...defaultProps} />);
  act(() => (capturedProps.onLinkClick as (edge: unknown) => void)(edge));
}

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

describe("GraphCanvas RNP details", () => {
  it("shows the declaration, named endpoints and verifiable provenance without scoring it", () => {
    openEdge(rnp);
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
      openEdge({ ...rnp, properties: { ...rnp.properties, source_url } });
      expect(screen.queryByRole("link")).not.toBeInTheDocument();
      expect(screen.getByText("organos.csv")).toBeInTheDocument();
    },
  );

  it("omits empty role and supports string endpoint IDs", () => {
    openEdge({ ...rnp, type: "SOCIO_DE", source: "p1", target: "p2",
      properties: { ...rnp.properties, cargo: " " } });
    expect(screen.getByRole("heading")).toHaveTextContent("Socio de");
    expect(screen.queryByText("Cargo declarado")).not.toBeInTheDocument();
    expect(screen.getByText("p1")).toBeInTheDocument();
  });

  it("preserves existing edge details and closes the panel", () => {
    openEdge({ type: "HAS_SANCTION", source: "p1", target: "s1", properties: {} });
    expect(screen.getByText("Confianza")).toBeInTheDocument();
    expect(screen.queryByText(/Vínculo declarado en RNP/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByText("Confianza")).not.toBeInTheDocument();
  });
});

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

it("keeps a clicked node card open for source interaction and dismisses it on background click", () => {
  vi.useFakeTimers();
  const node = { ...sampleData.nodes[2], x: 0, y: 0, properties: {
    source_url: "https://example.org/osce", sanction_source: "OSCE_TCP",
  } };
  const { rerender } = render(<GraphCanvas {...defaultProps} />);
  act(() => (capturedProps.onNodeClick as (node: unknown) => void)(node));
  act(() => {
    (capturedProps.onNodeHover as (node: unknown) => void)(null);
    vi.advanceTimersByTime(500);
  });
  const link = screen.getByRole("link", { name: /Abrir fuente/ });
  fireEvent.click(link);
  expect(link).toHaveAttribute("href", "https://example.org/osce");
  fireEvent.click(screen.getByRole("button", { name: "Cerrar ficha" }));
  expect(screen.queryByRole("link", { name: /Abrir fuente/ })).not.toBeInTheDocument();
  act(() => (capturedProps.onNodeClick as (node: unknown) => void)(node));
  act(() => (capturedProps.onBackgroundClick as () => void)());
  expect(screen.queryByRole("link", { name: /Abrir fuente/ })).not.toBeInTheDocument();
  act(() => (capturedProps.onNodeClick as (node: unknown) => void)(node));
  rerender(<GraphCanvas {...defaultProps} enabledTypes={new Set(["person", "company"])} />);
  expect(screen.queryByRole("link", { name: /Abrir fuente/ })).not.toBeInTheDocument();
});
