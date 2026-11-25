import { App } from "antd";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import KnowledgeGraphModal from "./KnowledgeGraphModal";

vi.mock("../../api/modules/knowledgeBases", () => ({
  knowledgeBasesApi: {
    getGraph: vi.fn().mockResolvedValue({
      stats: {
        built: false,
        entities: 0,
        relations: 0,
        documents_total: 0,
        documents_ready: 0,
        documents_partial: 0,
        documents_pending: 0,
        documents_failed: 0,
      },
      nodes: [],
      edges: [],
    }),
    getGraphEntity: vi.fn(),
  },
}));

describe("KnowledgeGraphModal beta badge", () => {
  it("marks the dialog title with the shared beta badge", async () => {
    render(
      <App>
        <KnowledgeGraphModal
          open
          kbId="kb1"
          kbName="Notes"
          canWrite={false}
          canBuild={false}
          onClose={() => {}}
        />
      </App>,
    );

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("knowledgeBases.graphTitle");
    expect(
      screen.getByLabelText("knowledgeBases.graphBetaTooltip"),
    ).toHaveTextContent("header.betaBadge");
  });
});
