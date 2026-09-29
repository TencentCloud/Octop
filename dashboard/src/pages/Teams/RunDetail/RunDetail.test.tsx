/**
 * T-20 acceptance: the three "not measured" states stay distinguishable, the two
 * AM-1/decision facts stay visible, and no component reaches the network directly.
 */

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RunDetail from "./index";

import * as client from "../../../api/modules/teamRuns";
import { isDecisionPending } from "../../../api/modules/teamRuns";
import ArtifactPanel, { indexFieldDisplay, ownersLabel } from "./ArtifactPanel";
import DecisionCard from "./DecisionCard";
import MetricsTab, { sectionMode } from "./MetricsTab";
import PeoplePanel, { memberLoads } from "./PeoplePanel";
import PhaseStepper, { skippedRolesOf } from "./PhaseStepper";
import { allSkippedRoles } from "./index";

const RUN_DIR = join(__dirname);

function t(key: string): string {
  return key;
}

describe("honest empty states (acceptance ②)", () => {
  it("an empty metric section says 暂无该事件族 and never renders 0", () => {
    render(
      <MetricsTab
        metrics={{
          sections: [
            {
              title: "轮次分布",
              lines: [],
              state: "empty",
              note: "事件族不存在",
            },
          ],
          rendered: "",
        }}
      />,
    );
    expect(screen.getByTestId("metric-empty-轮次分布")).toBeTruthy();
    expect(
      screen.getByTestId("metric-轮次分布").getAttribute("data-mode"),
    ).toBe("empty");
    expect(screen.queryByTestId("metric-proxy-轮次分布")).toBeNull();
  });

  it("measured / proxy / empty / partial are four distinguishable render modes", () => {
    expect(sectionMode("measured")).toBe("measured");
    expect(sectionMode("proxy")).toBe("proxy");
    expect(sectionMode("empty")).toBe("empty");
    expect(sectionMode("partial")).toBe("partial");
    // An unknown state must NOT pass as measured.
    expect(sectionMode("mystery" as never)).toBe("empty");
  });

  it("a null index field renders 待写入方 — distinct from a real 0", () => {
    const pending = indexFieldDisplay(null, t);
    expect(pending.pending).toBe(true);
    expect(pending.text).toBe("teamRuns.artifacts.awaitingWriter");
    // Falsy-but-real values stay visible: 0 is a measurement, absence is not.
    const zero = indexFieldDisplay(0, t);
    expect(zero.pending).toBe(false);
    expect(zero.text).toBe("0");
    const hash = indexFieldDisplay("abc123", t);
    expect(hash.pending).toBe(false);
  });

  it("artifact rows show pending-writer markers for the four T-45 fields", () => {
    render(
      <ArtifactPanel
        items={[
          {
            name: "TASKS.json",
            present: true,
            owners: [],
            revision: null,
            owner_role: null,
            phase: null,
            version: null,
            hash: null,
            created_at: null,
          },
        ]}
      />,
    );
    for (const field of ["phase", "version", "hash", "created_at"]) {
      expect(
        screen.getByTestId(`artifact-pending-TASKS.json-${field}`),
      ).toBeTruthy();
    }
  });

  it("owners semantics: [] = runtime only (a real value), null = unrestricted", () => {
    expect(ownersLabel([], t).runtimeOnly).toBe(true);
    expect(ownersLabel([], t).text).toBe("teamRuns.artifacts.runtimeOnly");
    expect(ownersLabel(null, t).text).toBe("teamRuns.artifacts.unrestricted");
    expect(ownersLabel(["pm", "qa"], t).text).toBe("pm / qa");
  });
});

describe("gate visibility (acceptance ③)", () => {
  it("skipped_roles are read out of gate_detail and rendered per phase", () => {
    expect(skippedRolesOf({ skipped_roles: ["docs", "sec"] })).toEqual([
      "docs",
      "sec",
    ]);
    expect(skippedRolesOf({})).toEqual([]);
    expect(skippedRolesOf(undefined)).toEqual([]);
    // A malformed payload must not crash the page.
    expect(skippedRolesOf({ skipped_roles: "docs" as never })).toEqual([]);

    render(
      <PhaseStepper
        phases={[
          {
            phase: "implement",
            seq: 5,
            status: "active",
            gate_detail: { skipped_roles: ["docs"] },
            entered_at: 1,
            passed_at: null,
          },
        ]}
        pendingDecision={null}
      />,
    );
    expect(screen.getByTestId("phase-skipped-implement").textContent).toContain(
      "docs",
    );
  });

  it("a pending decision badges the active phase instead of hiding it", () => {
    render(
      <PhaseStepper
        phases={[
          {
            phase: "方案确认",
            seq: 4,
            status: "active",
            gate_detail: {},
            entered_at: 1,
            passed_at: null,
          },
        ]}
        pendingDecision={{ decision_id: "d-1", status: "pending" }}
      />,
    );
    expect(screen.getByTestId("phase-parked-方案确认")).toBeTruthy();
  });

  it("allSkippedRoles dedupes across phases and keeps phase order", () => {
    const phases = [
      {
        phase: "a",
        seq: 0,
        status: "passed",
        gate_detail: { skipped_roles: ["docs"] },
        entered_at: null,
        passed_at: null,
      },
      {
        phase: "b",
        seq: 1,
        status: "passed",
        gate_detail: { skipped_roles: ["docs", "sec"] },
        entered_at: null,
        passed_at: null,
      },
    ] as never;
    expect(allSkippedRoles(phases)).toEqual(["docs", "sec"]);
  });

  it("DecisionCard states 'no pending decision' as its own state", () => {
    render(<DecisionCard pendingDecision={null} />);
    expect(screen.getByTestId("decision-none")).toBeTruthy();
  });

  it("DecisionCard invents no options when the payload carries none", () => {
    render(
      <DecisionCard
        pendingDecision={{
          decision_id: "d-9",
          kind: "tier",
          status: "pending",
        }}
      />,
    );
    expect(screen.getByTestId("decision-id").textContent).toBe("d-9");
    expect(screen.getByTestId("decision-no-options")).toBeTruthy();
    expect(screen.queryByTestId("decision-options")).toBeNull();
  });
});

describe("people load comes from the DB task board", () => {
  it("pair members with in-flight counts; an empty board is not 'all idle'", () => {
    const loads = memberLoads(
      [
        { role: "backend", agent_id: "a2", is_lead: false },
        { role: "pm", agent_id: "a1", is_lead: true },
      ],
      [
        { id: "T-1", owner: "backend", status: "doing" } as never,
        { id: "T-2", owner: "backend", status: "done" } as never,
      ],
    );
    expect(loads[0]).toMatchObject({ role: "backend", tasks: 2, inFlight: 1 });
    expect(loads[1]).toMatchObject({ role: "pm", tasks: 0, inFlight: 0 });

    render(
      <PeoplePanel
        members={[{ role: "pm", agent_id: "a1", is_lead: true }]}
        tasks={[]}
      />,
    );
    expect(screen.getByTestId("member-lead-pm")).toBeTruthy();
    expect(screen.getByTestId("people-board-empty")).toBeTruthy();
  });
});

describe("frontend boundary (acceptance ④)", () => {
  it("no RunDetail component calls fetch/axios directly", () => {
    const offenders: string[] = [];
    for (const file of readdirSync(RUN_DIR)) {
      if (!file.endsWith(".tsx") && !file.endsWith(".ts")) continue;
      if (file.endsWith(".test.tsx")) continue;
      const source = readFileSync(join(RUN_DIR, file), "utf8");
      // Only real call sites matter — a comment mentioning `fetch(` is not a call.
      for (const line of source.split("\n")) {
        const code = line.split("//")[0];
        if (/\bfetch\s*\(/.test(code) || /\baxios\b/.test(code))
          offenders.push(`${file}: ${line.trim()}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("the typed client covers all 18 of T-16's routes (acceptance ①)", () => {
    // 18 routes = 1 create + 1 list + 1 detail + 1 state + 1 advance + 2 tasks + 1 dispatch
    // + 1 metrics + 1 export + 1 check + 3 artifacts + 1 decision + 2 (:resume/:cancel).
    const required = [
      "createRun",
      "listRuns",
      "getRun",
      "getRunState",
      "advanceRun",
      "listTasks",
      "createTask",
      "patchTask",
      "dispatchTask",
      "getMetrics",
      "getExport",
      "checkRun",
      "listArtifacts",
      "getArtifact",
      "putArtifact",
      "decideRun",
      "resumeRun",
      "cancelRun",
    ] as const;
    expect(required).toHaveLength(18);
    for (const name of required) {
      expect(typeof client[name]).toBe("function");
    }
    expect(client.EXPORT_NAMES).toEqual([
      "TASKS.json",
      "任务看板.md",
      "STATE.json",
      "ROSTER.json",
    ]);
  });
});

// ───────────────────────── 端到端：能到 + 能工作（T-21 验收 ③）

/** Stub `fetch` (the real transport): the page runs its own requests through `request()`. */
function stubFetch(
  handlers: Record<string, { status: number; body: unknown }>,
) {
  const calls: string[] = [];
  // `BASE_URL` is injected by vite.config.ts (`define`), so it does not exist under
  // vitest — the real `request()` transport needs it. Stub the same empty value the
  // same-origin build uses.
  vi.stubGlobal("BASE_URL", "");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      const match = Object.keys(handlers).find((key) => url.includes(key));
      if (!match) {
        return new Response("not found", {
          status: 404,
          statusText: "Not Found",
        });
      }
      const { status, body } = handlers[match];
      return new Response(JSON.stringify(body), {
        status,
        statusText: status === 200 ? "OK" : "Error",
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return calls;
}

const RUN_FIXTURE = {
  run_id: "2026-09-28-145847",
  project_id: "p-1",
  team_agent_id: "team-1",
  goal: "只读投影导出",
  mode: "persist",
  deliverable: "code+artifacts",
  tier: "strict",
  status: "running",
  phase: "implement",
  room_thread_id: null,
  max_review_rounds: 3,
  created_at: 1756000000,
  updated_at: 1756000500,
  allowed_phases: ["review"],
  members: [{ role: "pm", agent_id: "a1", is_lead: true }],
  // 真实 pending payload 一定带 `status`（`run_service.raise_decision` 写 `"pending"`）——
  // 只有"存在与否"的旧 fixture 是不现实的，T-53 后按契约补上。
  pending_decision: { decision_id: "d-7", status: "pending", kind: "tier" },
  phases: [
    {
      phase: "implement",
      seq: 5,
      status: "active",
      gate_detail: { skipped_roles: ["docs"] },
      entered_at: 1756000100,
      passed_at: null,
    },
  ],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("end-to-end through the route element (T-21 acceptance ③)", () => {
  it("enters the page, issues real requests, and renders the existing run's state", async () => {
    const calls = stubFetch({
      "/state?section=check": {
        status: 200,
        body: {
          section: "check",
          check: { violations: ["verify_missing"], finding_reopened: null },
        },
      },
      "/tasks": { status: 200, body: { nodes: [], edges: [], violations: [] } },
      "/artifacts": { status: 200, body: { items: [] } },
      "/metrics": { status: 200, body: { sections: [], rendered: "" } },
      "/team/runs/2026-09-28-145847": { status: 200, body: RUN_FIXTURE },
    });
    render(<RunDetail runId="2026-09-28-145847" />);

    await waitFor(() => expect(screen.getByTestId("run-detail")).toBeTruthy());
    // 真实请求发生了（走 request() → fetch），且状态/阶段/门禁事实都上了屏。
    expect(calls.length).toBeGreaterThanOrEqual(4);
    // 全局 i18n mock 在有 fallback 时返回 fallback（生产里渲染的是 `teamRuns.runStatus.running` 的本地化文案）。
    expect(screen.getByTestId("run-status").textContent).toBe("running");
    expect(screen.getByTestId("gate-pending-decision")).toBeTruthy();
    expect(screen.getByTestId("gate-skipped-list").textContent).toContain(
      "docs",
    );
    expect(screen.getByTestId("gate-check-violations").textContent).toContain(
      "verify_missing",
    );
    expect(screen.getByTestId("phase-parked-implement")).toBeTruthy();
  });

  it("positive control: an unknown run shows a visible 404 state, never a blank page", async () => {
    stubFetch({}); // every request 404s
    render(<RunDetail runId="does-not-exist" />);

    await waitFor(() =>
      expect(screen.getByTestId("run-not-found")).toBeTruthy(),
    );
    // 不是白屏，也不是通用错误：这是**它自己的状态**。
    expect(screen.queryByTestId("run-error")).toBeNull();
    expect(screen.queryByTestId("run-detail")).toBeNull();
    expect(screen.getByTestId("run-not-found").textContent).toContain(
      "teamRuns.notFound.title",
    );
  });
});

// ───────────── T-53：决策拍板后（status="resolved"）页面不得继续"待拍板" ─────────────
//
// 后端契约（`run_service.py:1165` raise ⇒ `"status":"pending"`；`:1223` decide ⇒ **写回
// 同一个 payload** 并把 status 改成 `"resolved"`，而不是清除）⇒ `pending_decision`
// **一旦抛起就永不回 null**。所以"还有没有待拍板的事"只能看 `status`。

describe("decision lifecycle (T-53)", () => {
  const RESOLVED = {
    decision_id: "d-7",
    status: "resolved",
    kind: "tier",
    options: ["quick", "standard"],
    choice: "standard",
    note: "ok",
    resolved_at: 1756000999,
  };

  it("the predicate reads status, not presence", () => {
    expect(isDecisionPending({ status: "pending" })).toBe(true);
    expect(isDecisionPending(RESOLVED)).toBe(false);
    expect(isDecisionPending(null)).toBe(false);
    expect(isDecisionPending(undefined)).toBe(false);
    expect(isDecisionPending({})).toBe(false);
  });

  it("a resolved payload: no red bar, no parked phase, card says 'no pending decision'", () => {
    render(
      <PhaseStepper phases={RUN_FIXTURE.phases} pendingDecision={RESOLVED} />,
    );
    // 阶段条不得再标"待决策"。
    expect(screen.queryByTestId("phase-parked-implement")).toBeNull();
  });

  it("a resolved payload renders the card's 'no pending decision' state, not a confirm affordance", () => {
    render(
      <DecisionCard
        pendingDecision={RESOLVED}
        options={[{ id: "quick", label: "quick" }]}
      />,
    );
    expect(screen.getByTestId("decision-none")).toBeTruthy();
    expect(screen.queryByTestId("decision-card")).toBeNull();
    expect(screen.queryByTestId("decision-option-quick")).toBeNull();
  });

  it("page level: resolved ⇒ red bar gone and the clear line is shown", async () => {
    stubFetch({
      "/state?section=check": {
        status: 200,
        body: {
          section: "check",
          check: { violations: [], finding_reopened: null },
        },
      },
      "/tasks": { status: 200, body: { nodes: [], edges: [], violations: [] } },
      "/artifacts": { status: 200, body: { items: [] } },
      "/metrics": { status: 200, body: { sections: [], rendered: "" } },
      "/team/runs/2026-09-28-145847": {
        status: 200,
        body: {
          ...RUN_FIXTURE,
          pending_decision: RESOLVED,
          phases: [{ ...RUN_FIXTURE.phases[0], gate_detail: {} }],
        },
      },
    });
    render(<RunDetail runId="2026-09-28-145847" />);
    await waitFor(() => expect(screen.getByTestId("run-detail")).toBeTruthy());
    expect(screen.queryByTestId("gate-pending-decision")).toBeNull();
    expect(screen.queryByTestId("phase-parked-implement")).toBeNull();
    expect(screen.getByTestId("gate-clear")).toBeTruthy();
  });

  it("positive control: pending still shows the red bar + parked phase (unchanged)", async () => {
    stubFetch({
      "/state?section=check": {
        status: 200,
        body: {
          section: "check",
          check: { violations: [], finding_reopened: null },
        },
      },
      "/tasks": { status: 200, body: { nodes: [], edges: [], violations: [] } },
      "/artifacts": { status: 200, body: { items: [] } },
      "/metrics": { status: 200, body: { sections: [], rendered: "" } },
      "/team/runs/2026-09-28-145847": { status: 200, body: RUN_FIXTURE },
    });
    render(<RunDetail runId="2026-09-28-145847" />);
    await waitFor(() =>
      expect(screen.getByTestId("gate-pending-decision")).toBeTruthy(),
    );
    expect(screen.getByTestId("phase-parked-implement")).toBeTruthy();
  });

  it("positive control: a null payload also shows the clear line (unchanged)", async () => {
    stubFetch({
      "/state?section=check": {
        status: 200,
        body: {
          section: "check",
          check: { violations: [], finding_reopened: null },
        },
      },
      "/tasks": { status: 200, body: { nodes: [], edges: [], violations: [] } },
      "/artifacts": { status: 200, body: { items: [] } },
      "/metrics": { status: 200, body: { sections: [], rendered: "" } },
      "/team/runs/2026-09-28-145847": {
        status: 200,
        body: {
          ...RUN_FIXTURE,
          pending_decision: null,
          phases: [{ ...RUN_FIXTURE.phases[0], gate_detail: {} }],
        },
      },
    });
    render(<RunDetail runId="2026-09-28-145847" />);
    await waitFor(() => expect(screen.getByTestId("run-detail")).toBeTruthy());
    expect(screen.queryByTestId("gate-pending-decision")).toBeNull();
    expect(screen.getByTestId("gate-clear")).toBeTruthy();
  });
});

// ─────── T8-REV · FIND-1：计划写入被拒时上屏本地化文案，不是 request() 的原始信封 ───────
//
// `request()` 抛出的 message 形如 `Request failed: 422 Error - {json}`（`request.ts:366-371`），
// 所以写入路径必须经过 `apiErrorMessage`（`utils/apiError.ts:68-93`）：它读信封里的 `code`，
// 优先渲染 `apiErrors.<code>`。★ 本文件的 `t` 来自 vitest 的全局 react-i18next mock（无
// fallback ⇒ 返回 key），所以 `apiErrors.*` 分支在测试里回落到 `error.message`；生产里走的是
// 同一个调用点的 `apiErrors.*` 分支（`locales/zh.json` 的 `TEAM_PLAN_DRAFT_INVALID`）。
// 判别性：把 `setPlanError` 改回 `cause.message`，第一个用例立刻红。

describe("plan write refusal (T8-REV · FIND-1)", () => {
  const STAGED_DRAFT = {
    roles: ["pm"],
    planStatus: "staged",
    tasks: [{ id: "t1", title: "导出只读投影", owner: "pm", deps: [] }],
  };

  it("a 422 draft refusal shows localized copy, never request()'s raw envelope", async () => {
    stubFetch({
      // 放在最前：`:plan` 是 stage 路由自己的后缀，别被下面更宽的 run 路径先吃掉。
      ":plan": {
        status: 422,
        body: {
          error: {
            code: "TEAM_PLAN_DRAFT_INVALID",
            message: "计划草稿非法：任务负责人不在角色清单内",
            details: { code: "missing-id", path: ["tasks", "0", "owner"] },
          },
        },
      },
      "/state?section=check": {
        status: 200,
        body: {
          section: "check",
          check: { violations: [], finding_reopened: null },
        },
      },
      "/tasks": { status: 200, body: { nodes: [], edges: [], violations: [] } },
      "/artifacts": { status: 200, body: { items: [] } },
      "/metrics": { status: 200, body: { sections: [], rendered: "" } },
      "/team/runs/2026-09-28-145847": {
        status: 200,
        body: {
          ...RUN_FIXTURE,
          pending_decision: {
            decision_id: "d-7",
            status: "pending",
            kind: "tier",
            draft: STAGED_DRAFT,
          },
        },
      },
    });
    render(<RunDetail runId="2026-09-28-145847" />);
    await screen.findByTestId("run-detail");
    // DecisionCard 活在 `decision` 页签里，而 `Tabs` 没有 `defaultActiveKey`（默认第一个页签）
    // ⇒ 先切页签，编辑器与三个写入按钮才会挂载。页签标签在 i18n mock 下就是它的 key。
    const decisionTab = screen.getAllByText("teamRuns.tab.decision")[0];
    decisionTab.click();
    await screen.findByTestId("plan-stage");

    (screen.getByTestId("plan-stage") as HTMLButtonElement).click();

    const shown = (await screen.findByTestId("plan-error")).textContent ?? "";
    // 原始信封的签名一个都不许出现……
    expect(shown).not.toContain("Request failed");
    expect(shown).not.toContain("missing-id");
    // ……上屏的是给人看的本地化文案。
    expect(shown).toContain("计划草稿非法");
  });

  it("both plan-draft codes are consumed by the localized apiErrors.* path", async () => {
    const { apiErrorMessage } = await import("../../../utils/apiError");
    const zh: Record<string, string> = {
      TEAM_PLAN_DRAFT_INVALID: "计划草稿非法：任务负责人不在角色清单内",
      TEAM_PLAN_DRAFT_MISSING: "没有待批准的计划草稿",
    };
    const lookup = (key: string) => zh[key.replace("apiErrors.", "")] ?? key;
    const i18n = lookup as unknown as Parameters<typeof apiErrorMessage>[2];
    for (const code of ["TEAM_PLAN_DRAFT_INVALID", "TEAM_PLAN_DRAFT_MISSING"]) {
      const envelope = { error: { code, message: zh[code], details: {} } };
      const raw = `Request failed: 422 Error - ${JSON.stringify(envelope)}`;
      const shown = apiErrorMessage(new Error(raw), "fallback", i18n);
      expect(shown).toBe(zh[code]);
      expect(shown).not.toContain("Request failed");
    }
  });
});
