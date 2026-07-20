/**
 * AtomsList.test.tsx — paginated atom list with filter selects.
 *
 * What we cover:
 *   - mount → listAtoms with default offset/limit
 *   - row content rendered (assertion)
 *   - changing the kind select forwards candidate_type to the API
 *   - clicking a row opens the detail Drawer with verbatim_quote
 *   - empty state renders Empty
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { makeAtom, listAtomsResp } from "../../../test/memoryFixtures";

vi.mock("../../../api/modules/memoryDashboard", () => ({
  memoryDashboardApi: {
    listAtoms: vi.fn(),
  },
  isAtomDeprecated: (a: { deprecated_at?: string | null }) =>
    a.deprecated_at != null,
}));

import { memoryDashboardApi } from "../../../api/modules/memoryDashboard";
import AtomsList from "./AtomsList";

const api = vi.mocked(memoryDashboardApi, true);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("<AtomsList />", () => {
  it("loads with default pagination and renders atom rows", async () => {
    api.listAtoms.mockResolvedValue(
      listAtomsResp([
        makeAtom({ id: "atom-1", assertion: "用户喜欢喝美式咖啡。" }),
        makeAtom({ id: "atom-2", assertion: "用户来自上海。", kind: "Fact" }),
      ]),
    );

    render(<AtomsList agentId="ZYWZTD" />);

    await waitFor(() => {
      expect(screen.getByText("用户喜欢喝美式咖啡。")).toBeInTheDocument();
      expect(screen.getByText("用户来自上海。")).toBeInTheDocument();
    });

    expect(api.listAtoms).toHaveBeenCalledWith("ZYWZTD", {
      offset: 0,
      limit: 20,
    });
  });

  // Regression: deprecation state comes from deprecated_at because the backend has no status field.
  // Active atoms show the active label and deprecate action; deprecated atoms show the forgotten label only.
  it("derives active/deprecated from deprecated_at in the drawer", async () => {
    api.listAtoms.mockResolvedValue(
      listAtomsResp([
        makeAtom({ id: "live", assertion: "在用记忆。", deprecated_at: null }),
        makeAtom({
          id: "dead",
          assertion: "已弃用记忆。",
          deprecated_at: "2026-06-28T00:00:00Z",
        }),
      ]),
    );

    const user = userEvent.setup();
    render(<AtomsList agentId="ZYWZTD" />);

    await waitFor(() => {
      expect(screen.getByText("在用记忆。")).toBeInTheDocument();
    });

    // Active atom: drawer has the deprecate action.
    await user.click(screen.getByText("在用记忆。"));
    await waitFor(() => {
      expect(screen.getByText("弃用这条记忆")).toBeInTheDocument();
    });
    expect(screen.getByText("在用")).toBeInTheDocument();

    // Deprecated atom: no deprecate button, forgotten label is shown.
    await user.click(screen.getByText("已弃用记忆。"));
    await waitFor(() => {
      expect(screen.getAllByText("已忘记").length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.queryByText("弃用这条记忆")).not.toBeInTheDocument();
  });

  it("renders Empty when API returns no items", async () => {
    api.listAtoms.mockResolvedValue(listAtomsResp([]));
    render(<AtomsList agentId="ZYWZTD" />);
    await waitFor(() => {
      expect(api.listAtoms).toHaveBeenCalledTimes(1);
    });
    expect(
      await screen.findByText(/还没有记忆。开始对话后/),
    ).toBeInTheDocument();
  });

  it("opens the detail drawer when a row is clicked", async () => {
    api.listAtoms.mockResolvedValue(
      listAtomsResp([
        makeAtom({
          id: "atom-1",
          assertion: "用户喜欢喝美式咖啡。",
          verbatim_quote: "我每天早上都喝美式咖啡，奶咖伤胃",
        }),
      ]),
    );

    const user = userEvent.setup();
    render(<AtomsList agentId="ZYWZTD" />);

    await waitFor(() => {
      expect(screen.getByText("用户喜欢喝美式咖啡。")).toBeInTheDocument();
    });
    await user.click(screen.getByText("用户喜欢喝美式咖啡。"));

    await waitFor(() => {
      // Drawer renders verbatim_quote in a Paragraph. LineageStrip may also render
      // the same verbatim as a fallback source-conversation quote, so >1 match is possible.
      expect(
        screen.getAllByText(/每天早上都喝美式咖啡/).length,
      ).toBeGreaterThanOrEqual(1);
    });
  });
});
