import { Form } from "antd";
import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { listKnowledge, listInstances } = vi.hoisted(() => ({
  listKnowledge: vi.fn(),
  listInstances: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ id: 7 }),
}));

vi.mock("../../../api/modules/knowledgeBases", () => ({
  knowledgeBasesApi: { list: listKnowledge },
}));

vi.mock("../../../api/modules/connectors", () => ({
  connectorsApi: { listInstances },
}));

import ExpertComposerDefaultsFields from "./ExpertComposerDefaultsFields";

function renderFields(agentId?: string | null) {
  return render(
    <Form>
      <ExpertComposerDefaultsFields agentId={agentId} />
    </Form>,
  );
}

describe("ExpertComposerDefaultsFields", () => {
  beforeEach(() => {
    listKnowledge.mockReset();
    listInstances.mockReset();
    listKnowledge.mockResolvedValue([{ id: "kb1", name: "KB" }]);
    listInstances.mockResolvedValue([]);
  });

  it("loads local knowledge bases and connectors by default", async () => {
    renderFields();
    await waitFor(() => expect(listKnowledge).toHaveBeenCalled());
    expect(listKnowledge).toHaveBeenCalledWith(undefined);
    expect(listInstances).toHaveBeenCalledWith(undefined);
  });

  it("passes a peer agent id so pickers tunnel to the peer", async () => {
    const agentId = "bridge:c1:doctor";
    renderFields(agentId);
    await waitFor(() => expect(listKnowledge).toHaveBeenCalledWith(agentId));
    expect(listInstances).toHaveBeenCalledWith(agentId);
  });
});
