import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  listAtomsResp,
  listEntitiesResp,
  makeAtom,
  makeEntity,
} from "../../../test/memoryFixtures";

vi.mock("../../../api/modules/memoryDashboard", () => ({
  memoryDashboardApi: {
    listEntities: vi.fn(),
    listAtoms: vi.fn(),
    listJournal: vi.fn(),
  },
  isAtomDeprecated: (atom: { deprecated_at?: string | null }) =>
    atom.deprecated_at != null,
}));

import { memoryDashboardApi } from "../../../api/modules/memoryDashboard";
import MemoryTree from "./MemoryTree";

const api = vi.mocked(memoryDashboardApi, true);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("<MemoryTree />", () => {
  it("shows correction audit in the tree detail drawer", async () => {
    api.listEntities.mockResolvedValue(
      listEntitiesResp([
        makeEntity({
          id: "entity-project",
          canonical_name: "拼豆工作台",
          atom_count: 1,
        }),
      ]),
    );
    api.listAtoms.mockResolvedValue(
      listAtomsResp([
        makeAtom({
          id: "atom-corrected",
          entity_id: "entity-project",
          candidate_id: "",
          assertion: "企鹅图像已经调整。",
          verbatim_quote: "企鹅不像，需要重新调整。",
        }),
      ]),
    );
    api.listJournal.mockResolvedValue({
      items: [
        {
          id: "journal-edit",
          timestamp: "2026-09-07T08:00:00Z",
          action: "user_edit",
          actor: "user",
          target_atom_id: "atom-corrected",
          before: {
            assertion: "企鹅不像，需要重新调整。",
            atom_id: "atom-old",
          },
          after: {
            assertion: "企鹅图像已经调整。",
            atom_id: "atom-corrected",
          },
        },
      ],
      total: 1,
      has_more: false,
    });

    const user = userEvent.setup();
    render(<MemoryTree agentId="main" />);

    await user.click(await screen.findByText("拼豆工作台"));
    await user.click(await screen.findByText("企鹅图像已经调整。"));

    await waitFor(() => {
      expect(api.listJournal).toHaveBeenCalledWith("main", {
        action: "user_edit",
        target_atom_id: "atom-corrected",
        limit: 1,
      });
    });
    expect(await screen.findByText(/人工修正的记忆/)).toBeInTheDocument();
    expect(
      screen.getByText("修正前：企鹅不像，需要重新调整。"),
    ).toBeInTheDocument();
    expect(screen.getByText(/原始来源上下文：/)).toBeInTheDocument();
  });
});
