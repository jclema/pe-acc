import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";

import {
  getEntity,
  getEntityByElementId,
  type EntityDetail,
} from "@/api/client";
import { Spinner } from "@/components/common/Spinner";
import { GraphCanvas } from "@/components/graph/GraphCanvas";
import { ControlsSidebar } from "@/components/graph/ControlsSidebar";
import { AnalysisNav } from "@/components/analysis/AnalysisNav";
import { ConnectionsList } from "@/components/analysis/ConnectionsList";
import { EntityHeader } from "@/components/analysis/EntityHeader";
import { useGraphData } from "@/hooks/useGraphData";
import { useEntityAnalysisStore } from "@/stores/entityAnalysis";
import { useGraphExplorerStore } from "@/stores/graphExplorer";

import styles from "./EntityAnalysis.module.css";

const RECENT_KEY = "bracc_recent_analyses";
const MAX_RECENT = 10;

interface RecentAnalysis {
  entityId: string;
  name: string;
  type: string;
  exposure: number;
  timestamp: number;
}

function saveRecentAnalysis(entry: RecentAnalysis) {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    const list: RecentAnalysis[] = raw ? (JSON.parse(raw) as RecentAnalysis[]) : [];
    const filtered = list.filter((r) => r.entityId !== entry.entityId);
    filtered.unshift(entry);
    localStorage.setItem(
      RECENT_KEY,
      JSON.stringify(filtered.slice(0, MAX_RECENT)),
    );
  } catch {
    // localStorage unavailable
  }
}

export function EntityAnalysis() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { entityId } = useParams<{ entityId: string }>();
  const id = entityId ?? "";

  // Analysis store
  const {
    activeTab,
    setActiveTab,
    selectedNodeId,
    setSelectedNodeId,
    hoveredNodeId,
    setHoveredNodeId,
    highlightedNodeIds,
  } = useEntityAnalysisStore();

  // Graph explorer store (for graph controls)
  const graphStore = useGraphExplorerStore();

  // Data fetching
  const [entity, setEntity] = useState<EntityDetail | null>(null);
  const [entityLoading, setEntityLoading] = useState(true);
  const { data: graphData, loading: graphLoading } = useGraphData(id, graphStore.depth);
  const isPublicIdentifier = /^\d{11}$/.test(id) || /^\d{14}$/.test(id);

  // Fetch entity only on mount — patterns and baseline are deferred
  useEffect(() => {
    if (!id) return;
    setEntityLoading(true);

    const request = isPublicIdentifier ? getEntity(id) : getEntityByElementId(id);

    request
      .then((ent) => {
        setEntity(ent);
      })
      .catch(() => {
        // Error handled by component (shows notFound)
      })
      .finally(() => setEntityLoading(false));
  }, [id, isPublicIdentifier]);

  // Save to recent analyses
  useEffect(() => {
    if (entity) {
      const rawName =
        entity.properties.legal_name ??
        entity.properties.trade_name ??
        entity.properties.nome ??
        entity.properties.razao_social ??
        entity.properties.name ??
        entity.properties.title ??
        entity.id;
      const name = typeof rawName === "string" ? rawName : String(rawName);
      saveRecentAnalysis({
        entityId: entity.id,
        name,
        type: entity.type,
        exposure: 0,
        timestamp: Date.now(),
      });
    }
  }, [entity]);

  // Reset graph store on entity change
  useEffect(() => {
    graphStore.reset();
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Graph data derivatives
  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    if (graphData) {
      for (const node of graphData.nodes) {
        counts[node.type] = (counts[node.type] ?? 0) + 1;
      }
    }
    return counts;
  }, [graphData]);

  const relTypeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    if (graphData) {
      for (const edge of graphData.edges) {
        counts[edge.type] = (counts[edge.type] ?? 0) + 1;
      }
    }
    return counts;
  }, [graphData]);

  // Combine selected + highlighted for graph display
  const graphSelectedIds = useMemo(() => {
    const ids = new Set(highlightedNodeIds);
    if (selectedNodeId) ids.add(selectedNodeId);
    return ids;
  }, [selectedNodeId, highlightedNodeIds]);

  const handleBack = useCallback(() => {
    void navigate(-1);
  }, [navigate]);

  const handleNodeClick = useCallback(
    (nodeId: string) => {
      setSelectedNodeId(nodeId);
      useEntityAnalysisStore.getState().setRightPanelTab("detail");
    },
    [setSelectedNodeId],
  );

  const handleNodeDeselect = useCallback(() => {
    setSelectedNodeId(null);
  }, [setSelectedNodeId]);

  if (entityLoading) {
    return (
      <div className={styles.loading}>
        <Spinner variant="scan" size="lg" />
      </div>
    );
  }

  if (!entity) {
    return (
      <div className={styles.notFound}>
        <p>{t("analysis.entityNotFound")}</p>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <EntityHeader
        entity={entity}
        exposure={null}
        onBack={handleBack}
      />

      <div className={styles.body}>
        <AnalysisNav activeTab={activeTab} onTabChange={setActiveTab} />

        <main className={styles.center}>
          {activeTab === "graph" && (
            <div className={styles.graphArea}>
              <div className={styles.graphSidebar}>
                <ControlsSidebar
                  collapsed={graphStore.sidebarCollapsed}
                  onToggle={graphStore.toggleSidebar}
                  depth={graphStore.depth}
                  onDepthChange={graphStore.setDepth}
                  enabledTypes={graphStore.enabledTypes}
                  onToggleType={graphStore.toggleType}
                  enabledRelTypes={graphStore.enabledRelTypes}
                  onToggleRelType={graphStore.toggleRelType}
                  typeCounts={typeCounts}
                  relTypeCounts={relTypeCounts}
                />
              </div>
              <div className={styles.graphCanvas}>
                {graphLoading && (
                  <div className={styles.graphOverlay}>
                    <Spinner variant="scan" size="md" />
                  </div>
                )}
                {graphData && (
                  <GraphCanvas
                    data={graphData}
                    centerId={id}
                    enabledTypes={graphStore.enabledTypes}
                    enabledRelTypes={graphStore.enabledRelTypes}
                    hiddenNodeIds={graphStore.hiddenNodeIds}
                    selectedNodeIds={graphSelectedIds}
                    hoveredNodeId={hoveredNodeId}
                    layoutMode={graphStore.layoutMode}
                    onNodeClick={handleNodeClick}
                    onNodeDeselect={handleNodeDeselect}
                    onNodeHover={setHoveredNodeId}
                    onNodeRightClick={() => {}}
                    onLayoutChange={graphStore.setLayoutMode}
                    onFullscreen={graphStore.toggleFullscreen}
                    sidebarCollapsed={graphStore.sidebarCollapsed}
                  />
                )}
              </div>
            </div>
          )}

          {activeTab === "connections" && graphData && (
            <ConnectionsList
              nodes={graphData.nodes}
              centerId={id}
              selectedNodeId={selectedNodeId}
              onSelectNode={handleNodeClick}
            />
          )}

        </main>
      </div>
    </div>
  );
}
