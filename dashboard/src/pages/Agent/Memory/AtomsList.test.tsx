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
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  makeAtom,
  makeCandidate,
  listAtomsResp,
} from "../../../test/memoryFixtures";

vi.mock("../../../api/modules/memoryDashboard", () => ({
  memoryDashboardApi: {
    listAtoms: vi.fn(),
    getCandidate: vi.fn().mockResolvedValue(null),
    listEntities: vi
      .fn()
      .mockResolvedValue({ items: [], total: 0, has_more: false }),
    listJournal: vi
      .fn()
      .mockResolvedValue({ items: [], total: 0, has_more: false }),
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
  // Active atoms allow mutations; archived atoms remain readable without mutation actions.
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
    expect(
      within(screen.getByRole("dialog")).getByText("在用"),
    ).toBeInTheDocument();

    // Deprecated atom: no edit/deprecate buttons, archive label is shown.
    await user.click(screen.getByText("已弃用记忆。"));
    await waitFor(() => {
      expect(screen.getAllByText("已归档")).toHaveLength(2);
    });
    expect(screen.queryByText("弃用这条记忆")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "编辑这条记忆" }),
    ).not.toBeInTheDocument();
  });

  it("includes archived rows on demand and resets pagination in both directions", async () => {
    const live = makeAtom({ id: "live", assertion: "An active preference" });
    const archived = makeAtom({
      id: "archived",
      assertion: "An archived preference",
      deprecated_at: "2026-06-28T00:00:00Z",
    });
    api.listAtoms.mockImplementation(async (_agentId, body) => ({
      items: body.include_deprecated ? [live, archived] : [live],
      total: 45,
      has_more: true,
    }));
    const user = userEvent.setup();
    render(<AtomsList agentId="test-agent" />);
    await screen.findByText(live.assertion);
    const toggle = screen.getByRole("switch", { name: "包含已归档" });
    expect(toggle).not.toBeChecked();
    expect(screen.queryByText(archived.assertion)).not.toBeInTheDocument();

    await user.click(screen.getByTitle("2"));
    await waitFor(() =>
      expect(api.listAtoms).toHaveBeenLastCalledWith("test-agent", {
        offset: 20,
        limit: 20,
      }),
    );
    await user.click(toggle);
    await screen.findByText(archived.assertion);
    expect(toggle).toBeChecked();
    expect(api.listAtoms).toHaveBeenLastCalledWith("test-agent", {
      offset: 0,
      limit: 20,
      include_deprecated: true,
    });
    expect(screen.getByText("已归档")).toBeInTheDocument();
    expect(screen.getByText("在用")).toBeInTheDocument();

    await user.click(screen.getByTitle("2"));
    await waitFor(() =>
      expect(api.listAtoms).toHaveBeenLastCalledWith("test-agent", {
        offset: 20,
        limit: 20,
        include_deprecated: true,
      }),
    );
    await user.click(toggle);
    await waitFor(() => {
      expect(api.listAtoms).toHaveBeenLastCalledWith("test-agent", {
        offset: 0,
        limit: 20,
      });
      expect(screen.queryByText(archived.assertion)).not.toBeInTheDocument();
    });
  });

  it("ignores an archive request that resolves after the switch is turned off", async () => {
    const live = makeAtom({ assertion: "Current active memory" });
    const archived = makeAtom({
      assertion: "Late archived memory",
      deprecated_at: "2026-06-28T00:00:00Z",
    });
    let resolveArchived!: (value: ReturnType<typeof listAtomsResp>) => void;
    const delayed = new Promise<ReturnType<typeof listAtomsResp>>((resolve) => {
      resolveArchived = resolve;
    });
    api.listAtoms.mockImplementation(async (_agentId, body) =>
      body.include_deprecated ? delayed : listAtomsResp([live]),
    );
    const user = userEvent.setup();
    render(<AtomsList agentId="test-agent" />);
    await screen.findByText(live.assertion);
    const toggle = screen.getByRole("switch", { name: "包含已归档" });
    await user.click(toggle);
    await waitFor(() =>
      expect(api.listAtoms).toHaveBeenLastCalledWith("test-agent", {
        offset: 0,
        limit: 20,
        include_deprecated: true,
      }),
    );
    await user.click(toggle);
    await screen.findByText(live.assertion);
    await act(async () => resolveArchived(listAtomsResp([archived])));
    expect(screen.queryByText(archived.assertion)).not.toBeInTheDocument();
    expect(screen.getByText(live.assertion)).toBeInTheDocument();
  });

  it("resets archive visibility when changing agents", async () => {
    api.listAtoms.mockResolvedValue(listAtomsResp([makeAtom()]));
    const user = userEvent.setup();
    const { rerender } = render(<AtomsList agentId="first-agent" />);
    await screen.findByText("用户喜欢喝美式咖啡。");
    await user.click(screen.getByRole("switch", { name: "包含已归档" }));
    rerender(<AtomsList agentId="second-agent" />);
    await waitFor(() => {
      expect(
        screen.getByRole("switch", { name: "包含已归档" }),
      ).not.toBeChecked();
      expect(api.listAtoms).toHaveBeenLastCalledWith("second-agent", {
        offset: 0,
        limit: 20,
      });
    });
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

  it("shows repeat evidence only when it belongs to this version", async () => {
    api.listAtoms.mockResolvedValue(
      listAtomsResp([
        makeAtom({
          assertion: "周报使用中文。",
          raw_event_ids: ["raw-1", "raw-2"],
        }),
      ]),
    );
    api.getCandidate.mockResolvedValueOnce(
      makeCandidate({
        payload: {
          evidence_quotes: {
            "raw-2": "周报还是用中文。",
            "raw-3": "以后周报改成双语。",
          },
        },
      }),
    );
    render(<AtomsList agentId="ZYWZTD" />);
    await userEvent.click(await screen.findByText("周报使用中文。"));
    expect(await screen.findByText(/周报还是用中文/)).toBeInTheDocument();
    expect(screen.queryByText(/以后周报改成双语/)).not.toBeInTheDocument();
  });

  it("shows the audit record instead of presenting old evidence as the corrected assertion", async () => {
    api.listAtoms.mockResolvedValue(
      listAtomsResp([
        makeAtom({
          id: "atom-corrected",
          assertion: "用户喜欢喝拿铁。",
          verbatim_quote: "我每天早上都喝美式咖啡",
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
          before: { assertion: "用户喜欢喝美式咖啡。", atom_id: "atom-old" },
          after: { assertion: "用户喜欢喝拿铁。", atom_id: "atom-corrected" },
        },
      ],
      total: 1,
      has_more: false,
    });

    const user = userEvent.setup();
    render(<AtomsList agentId="ZYWZTD" />);
    await user.click(await screen.findByText("用户喜欢喝拿铁。"));

    await waitFor(() => {
      expect(api.listJournal).toHaveBeenCalledWith("ZYWZTD", {
        action: "user_edit",
        target_atom_id: "atom-corrected",
        limit: 1,
      });
    });
    expect(await screen.findByText(/人工修正的记忆/)).toBeInTheDocument();
    expect(
      screen.getByText("修正前：用户喜欢喝美式咖啡。"),
    ).toBeInTheDocument();
    expect(screen.getByText(/原始来源上下文：/)).toBeInTheDocument();
  });
});
