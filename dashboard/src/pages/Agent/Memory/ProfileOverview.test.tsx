import "@testing-library/jest-dom/vitest";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

import {
  makeAtom,
  makeEntity,
  listAtomsResp,
  statsCountsFixture,
  terminalAtomResp,
  terminalEntityResp,
} from "../../../test/memoryFixtures";

vi.mock("../../../api/modules/memoryDashboard", () => ({
  memoryDashboardApi: {
    terminalAboutMe: vi.fn(),
    terminalCurrentFocus: vi.fn(),
    terminalThingsYouToldMe: vi.fn(),
    terminalEntities: vi.fn(),
    statsCounts: vi.fn(),
    listAtoms: vi.fn(),
  },
}));

import { memoryDashboardApi } from "../../../api/modules/memoryDashboard";
import ProfileOverview from "./ProfileOverview";

const api = vi.mocked(memoryDashboardApi, true);

beforeEach(() => {
  vi.clearAllMocks();
});

function stubProfile() {
  api.terminalAboutMe.mockResolvedValue(
    terminalAtomResp([makeAtom({ id: "a1", assertion: "你只喝美式咖啡。" })]),
  );
  api.terminalCurrentFocus.mockResolvedValue(
    terminalAtomResp([
      makeAtom({
        id: "a2",
        assertion: "你正在写记忆模块的设计文档。",
        kind: "Task",
      }),
    ]),
  );
  api.terminalThingsYouToldMe.mockResolvedValue(
    terminalAtomResp([
      makeAtom({ id: "a3", assertion: "你出生于1995年。", kind: "Fact" }),
    ]),
  );
  api.terminalEntities.mockResolvedValue(
    terminalEntityResp([
      makeEntity({
        id: "e1",
        canonical_name: "Bo5heng项目",
        entity_type: "Project",
      }),
    ]),
  );
  api.statsCounts.mockResolvedValue(
    statsCountsFixture({ atoms: 127, entities: 18 }),
  );
  api.listAtoms.mockResolvedValue(
    listAtomsResp([
      makeAtom({ id: "a1", confidence: "high" }),
      makeAtom({ id: "a2", confidence: "medium" }),
    ]),
  );
}

describe("<ProfileOverview />", () => {
  it("fans out to profile endpoints and renders the four profile cards", async () => {
    stubProfile();

    render(<ProfileOverview agentId="ZYWZTD" />);

    await waitFor(() => {
      expect(screen.getAllByText(/用户画像/).length).toBeGreaterThan(0);
    });

    expect(screen.getByText(/只喝美式咖啡/)).toBeInTheDocument();
    expect(screen.getByText(/记忆模块的设计文档/)).toBeInTheDocument();
    expect(screen.getByText(/出生于1995年/)).toBeInTheDocument();
    expect(screen.getByText("Bo5heng项目")).toBeInTheDocument();
    expect(screen.getByText("关于你")).toBeInTheDocument();
    expect(screen.getByText("当前重点")).toBeInTheDocument();
    expect(screen.getByText("你提到的事实")).toBeInTheDocument();
    expect(screen.getByText("关键人事物")).toBeInTheDocument();

    expect(api.terminalAboutMe).toHaveBeenCalledWith("ZYWZTD", 12);
    expect(api.terminalCurrentFocus).toHaveBeenCalledWith("ZYWZTD", 12);
    expect(api.terminalThingsYouToldMe).toHaveBeenCalledWith("ZYWZTD", 12);
    expect(api.terminalEntities).toHaveBeenCalledWith("ZYWZTD", 12);
    expect(api.statsCounts).toHaveBeenCalledWith("ZYWZTD");
  });

  it("survives partial endpoint failures", async () => {
    api.terminalAboutMe.mockRejectedValue(new Error("about me boom"));
    api.terminalCurrentFocus.mockResolvedValue(terminalAtomResp([]));
    api.terminalThingsYouToldMe.mockResolvedValue(terminalAtomResp([]));
    api.terminalEntities.mockResolvedValue(terminalEntityResp([]));
    api.statsCounts.mockResolvedValue(statsCountsFixture());
    api.listAtoms.mockResolvedValue(listAtomsResp([]));

    render(<ProfileOverview agentId="ZYWZTD" />);

    await waitFor(() => {
      expect(screen.getAllByText(/用户画像/).length).toBeGreaterThan(0);
    });
    expect(screen.getByText(/Octop 还在了解你/)).toBeInTheDocument();
  });

  it("caps a section at 6 rows and shows 查看全部 that calls onViewAll", async () => {
    const many = Array.from({ length: 8 }, (_, i) =>
      makeAtom({ id: `m${i}`, assertion: `关于你条目${i + 1}` }),
    );
    api.terminalAboutMe.mockResolvedValue(terminalAtomResp(many));
    api.terminalCurrentFocus.mockResolvedValue(terminalAtomResp([]));
    api.terminalThingsYouToldMe.mockResolvedValue(terminalAtomResp([]));
    api.terminalEntities.mockResolvedValue(terminalEntityResp([]));
    api.statsCounts.mockResolvedValue(statsCountsFixture());
    api.listAtoms.mockResolvedValue(listAtomsResp([]));

    const onViewAll = vi.fn();
    render(<ProfileOverview agentId="ZYWZTD" onViewAll={onViewAll} />);

    await waitFor(() => {
      expect(screen.getByText("关于你条目1")).toBeInTheDocument();
    });
    // Visible rows are capped at 6: the 6th row exists, the 7th does not.
    expect(screen.getByText("关于你条目6")).toBeInTheDocument();
    expect(screen.queryByText("关于你条目7")).not.toBeInTheDocument();

    const viewAll = screen.getByRole("button", { name: /查看全部/ });
    fireEvent.click(viewAll);
    expect(onViewAll).toHaveBeenCalledTimes(1);
  });

  it("does not call endpoints when agentId is empty", () => {
    render(<ProfileOverview agentId="" />);
    expect(api.terminalAboutMe).not.toHaveBeenCalled();
    expect(api.statsCounts).not.toHaveBeenCalled();
  });

  it("refresh button triggers another profile fan-out", async () => {
    stubProfile();

    render(<ProfileOverview agentId="ZYWZTD" />);

    await waitFor(() => {
      expect(api.statsCounts).toHaveBeenCalledTimes(1);
    });

    const refreshBtn = screen.getByRole("button");
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(api.statsCounts).toHaveBeenCalledTimes(2);
      expect(api.terminalAboutMe).toHaveBeenCalledTimes(2);
    });
  });
});
