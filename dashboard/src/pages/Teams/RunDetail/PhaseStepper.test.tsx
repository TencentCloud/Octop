/**
 * T-25 ② —— `PhaseStepper` 的三态与"不静默丢弃"契约（T-20 的组件，T-25 的用例）。
 *
 * 覆盖的契约（对 `TASKS.json · T-25` 的 acceptance：**skipped / 挂起 / 正常**三态）：
 *
 * 1. **正常态**：九个阶段按给定顺序全渲染，各自带状态标签；没有裁剪、没有挂起时
 *    **不**渲染那两个块（空态不是"隐藏的错误"）。
 * 2. **skipped 态**：`gate_detail.skipped_roles` 逐个渲染成**可见标签** —— 这是 AM-1
 *    硬要求「被裁可见、不静默丢弃」在 UI 上的唯一面孔，不能塌缩成一个计数。
 * 3. **挂起态**："是否在等用户"由**共用谓词** `teamRuns.isDecisionPending`（`status === "pending"`）
 *    裁决，**只有 `status === "active"` 的那个阶段**打「待决策」徽标。⇒ 已决的 payload
 *    留在 run 上时**不得**继续显示挂起（否则 stepper 会读成"在等一个不存在的东西"）。
 * 4. `gate_detail` 里**除 `skipped_roles` 以外**的键也要显示（同样不得静默丢弃）；
 *    空 `gate_detail` 则不显示那一行。
 * 5. 标签回退：连字符阶段名与 CJK 阶段名走**别名键**，未知值回退成原始值
 *    （永不产出空标签）。
 *
 * 说明：`react-i18next` 已被 `src/test/setup.ts` 全局 mock 成"有 fallback 就返回 fallback"，
 * 所以组件渲染出来的是**原始阶段名/状态**；而纯函数用例我改用**记录键的 stub `t`**，
 * 直接断言 i18n **键**（真正的契约），不依赖 mock 的取值方式。
 */

import { render, screen } from "@testing-library/react";
import type { TFunction } from "i18next";
import { describe, expect, it } from "vitest";

import {
  isDecisionPending,
  type PhaseWire,
} from "../../../api/modules/teamRuns";
import PhaseStepper, {
  gateDetailKeys,
  phaseLabel,
  phaseStatusLabel,
  skippedRolesOf,
} from "./PhaseStepper";

/** The nine phases of the pipeline (mirrors `teamRuns.phaseName` keys + the two aliases). */
const ALL_PHASES = [
  "clarify",
  "research",
  "design",
  "spec-review",
  "方案确认",
  "implement",
  "review",
  "test",
  "deliver",
] as const;

function phase(
  name: string,
  seq: number,
  status: string,
  gate_detail: Record<string, unknown> = {},
): PhaseWire {
  return {
    phase: name,
    seq,
    status,
    gate_detail,
    entered_at: 1,
    passed_at: null,
  } as PhaseWire;
}

/**
 * A `t` that records every key it is asked for and echoes the fallback (never empty).
 *
 * `PhaseStepper` 的纯函数收 `Translate = TFunction`，而 `TFunction` 带一个**幻影品牌**
 * `$TFunctionBrand` —— 任何手写 stub 都无法结构化满足它，所以这里用一次**有说明的**断言
 * 把它标成 `TFunction`（运行时就是上面那个纯函数，没有任何行为被绕开）。
 * 注意：`.test.tsx` 被 `tsconfig.app.json` 排除在 `tsc -b` 之外，这个类型错误只有单独
 * typecheck 才看得见（本次交付已用临时 tsconfig 补跑过）。
 */
function recorder(): { t: TFunction; keys: string[] } {
  const keys: string[] = [];
  const t = ((key: string, fallback?: string): string => {
    keys.push(key);
    return fallback ?? key;
  }) as unknown as TFunction;
  return { t, keys };
}

// ── 1. 正常态 ──────────────────────────────────────────────────────────────

describe("正常态：九个阶段全渲染，且不渲染不存在的块", () => {
  it("renders all nine phases in the order given, each with a status tag", () => {
    const phases = ALL_PHASES.map((name, seq) =>
      phase(name, seq, seq === 5 ? "active" : "pending"),
    );
    render(<PhaseStepper phases={phases} pendingDecision={null} />);

    const rendered = Array.from(
      screen.getByTestId("phase-stepper").children,
    ).map((el) => el.getAttribute("data-testid"));
    expect(rendered).toEqual(ALL_PHASES.map((name) => `phase-${name}`));

    for (const name of ALL_PHASES) {
      expect(screen.getByTestId(`phase-status-${name}`)).toBeTruthy();
      // data-status 是机器可读的那一份，必须与 wire 状态一致。
      expect(
        screen.getByTestId(`phase-${name}`).getAttribute("data-status"),
      ).toBe(name === "implement" ? "active" : "pending");
    }
  });

  it("a run with nothing cut and nothing pending shows neither block (empty is not an error)", () => {
    render(
      <PhaseStepper
        phases={[phase("clarify", 0, "active")]}
        pendingDecision={null}
      />,
    );

    expect(screen.queryByTestId("phase-skipped-clarify")).toBeNull();
    expect(screen.queryByTestId("phase-parked-clarify")).toBeNull();
    expect(screen.queryByTestId("phase-gate-detail-clarify")).toBeNull();
  });

  it("an empty phase list renders the empty stepper shell, not a crash", () => {
    render(<PhaseStepper phases={[]} pendingDecision={null} />);

    expect(screen.getByTestId("phase-stepper").children).toHaveLength(0);
  });
});

// ── 2. skipped 态（AM-1「被裁可见」）────────────────────────────────────────

describe("skipped 态：被裁角色逐个可见，不塌缩成计数", () => {
  it("renders one visible tag per cut role", () => {
    render(
      <PhaseStepper
        phases={[
          phase("implement", 5, "active", {
            skipped_roles: ["docs", "sec", "ui"],
          }),
        ]}
        pendingDecision={null}
      />,
    );

    const block = screen.getByTestId("phase-skipped-implement");
    for (const role of ["docs", "sec", "ui"]) {
      expect(block.textContent).toContain(role);
    }
    // 不是只显示一个数字：三个角色必须都能读到。
    expect(block.querySelectorAll(".ant-tag")).toHaveLength(3);
  });

  it("shows nothing for a phase whose cuts are an empty list", () => {
    render(
      <PhaseStepper
        phases={[phase("review", 6, "passed", { skipped_roles: [] })]}
        pendingDecision={null}
      />,
    );

    expect(screen.queryByTestId("phase-skipped-review")).toBeNull();
  });

  it("skippedRolesOf keeps only non-empty strings and survives malformed payloads", () => {
    expect(skippedRolesOf({ skipped_roles: ["docs"] })).toEqual(["docs"]);
    expect(skippedRolesOf({ skipped_roles: [] })).toEqual([]);
    expect(skippedRolesOf({})).toEqual([]);
    expect(skippedRolesOf(undefined)).toEqual([]);
    expect(skippedRolesOf({ skipped_roles: "docs" as never })).toEqual([]);
    // 数组里的脏值被丢掉，但同一数组里的合法值保留。
    expect(
      skippedRolesOf({ skipped_roles: ["docs", "", 7, null] as never }),
    ).toEqual(["docs"]);
  });
});

// ── 3. 挂起态 ──────────────────────────────────────────────────────────────

describe("挂起态：只有 active 阶段打「待决策」徽标", () => {
  /**
   * 真源 = `teamRuns.ts · isDecisionPending @176-180`（`status === "pending"`），
   * 由组件与 `index.tsx @119` 共用。这里**不手写"看起来像挂起"的 shape**，
   * 而是先断言谓词成立，再把它喂给组件 —— 免得两边对"什么算挂起"各有一套口径。
   * （本条 rebase 的原因：`PhaseStepper.tsx` 在我写测试期间被改成走该谓词，
   *   旧的 `{ decision_id }` 形状已不再算挂起。）
   */
  const parked = { status: "pending", decision_id: "d-1" };

  it("precondition: the fixture really is what the shared predicate calls pending", () => {
    expect(isDecisionPending(parked)).toBe(true);
    // 已决 / 空 / null 都不是挂起 —— 后端会把已决的 payload 留在 run 上。
    expect(isDecisionPending({ status: "resolved", decision_id: "d-1" })).toBe(
      false,
    );
    expect(isDecisionPending({ decision_id: "d-1" })).toBe(false);
    expect(isDecisionPending({})).toBe(false);
    expect(isDecisionPending(null)).toBe(false);
    expect(isDecisionPending(undefined)).toBe(false);
  });

  it("badges the active phase and only the active phase", () => {
    render(
      <PhaseStepper
        phases={[
          phase("clarify", 0, "passed"),
          phase("research", 1, "active"),
          phase("design", 2, "pending"),
        ]}
        pendingDecision={parked}
      />,
    );

    expect(screen.getByTestId("phase-parked-research")).toBeTruthy();
    expect(screen.queryByTestId("phase-parked-clarify")).toBeNull();
    expect(screen.queryByTestId("phase-parked-design")).toBeNull();
  });

  it("a cleared decision removes the badge without touching the phases", () => {
    const phases = [phase("research", 1, "active")];
    render(<PhaseStepper phases={phases} pendingDecision={null} />);

    expect(screen.queryByTestId("phase-parked-research")).toBeNull();
    expect(screen.getByTestId("phase-status-research").textContent).toBe(
      "active",
    );
  });

  it("a RESOLVED payload on the run does not keep a phase looking parked", () => {
    // 这正是 `isDecisionPending` 被引入要防的假象：run 上仍留着已决 payload，
    // 但没有任何东西在等用户 ⇒ 不能打徽标。
    render(
      <PhaseStepper
        phases={[phase("review", 6, "active")]}
        pendingDecision={{ status: "resolved", decision_id: "d-1" }}
      />,
    );

    expect(screen.queryByTestId("phase-parked-review")).toBeNull();
    expect(screen.getByTestId("phase-status-review").textContent).toBe(
      "active",
    );
  });

  it("a pending decision with no active phase badges nothing (no invented target)", () => {
    render(
      <PhaseStepper
        phases={[phase("test", 7, "passed")]}
        pendingDecision={parked}
      />,
    );

    expect(screen.queryByTestId("phase-parked-test")).toBeNull();
  });

  it("the parked badge carries the i18n key, not an empty label", () => {
    render(
      <PhaseStepper
        phases={[phase("review", 6, "active")]}
        pendingDecision={parked}
      />,
    );

    expect(screen.getByTestId("phase-parked-review").textContent).toBe(
      "teamRuns.phase.pendingDecision",
    );
  });
});

// ── 4. gate_detail 的其它键也不静默丢弃 ────────────────────────────────────

describe("gate_detail：除 skipped_roles 之外的键照样可见", () => {
  it("lists the remaining keys and omits skipped_roles from that list", () => {
    const detail = { skipped_roles: ["docs"], tier_cap: 4, budget: "exceeded" };

    expect(gateDetailKeys(detail)).toEqual(["tier_cap", "budget"]);
    expect(gateDetailKeys(undefined)).toEqual([]);
    expect(gateDetailKeys({ skipped_roles: ["docs"] })).toEqual([]);

    render(
      <PhaseStepper
        phases={[phase("design", 2, "active", detail)]}
        pendingDecision={null}
      />,
    );

    const line = screen.getByTestId("phase-gate-detail-design");
    expect(line.textContent).toContain("teamRuns.gate.detailLabel");
    expect(line.textContent).toContain("tier_cap");
    expect(line.textContent).toContain("budget");
    expect(line.textContent).not.toContain("skipped_roles");
  });
});

// ── 5. 标签回退（键是契约）──────────────────────────────────────────────────

describe("标签：别名键 + 永不空标签", () => {
  it("maps the hyphen and CJK phases to their key-safe aliases", () => {
    const { t, keys } = recorder();

    expect(phaseLabel("spec-review", t)).toBe("spec-review");
    expect(phaseLabel("方案确认", t)).toBe("方案确认");
    expect(keys).toEqual([
      "teamRuns.phaseName.spec_review",
      "teamRuns.phaseName.confirm",
    ]);
  });

  it("falls back to the raw value for unknown phases and statuses", () => {
    const { t, keys } = recorder();

    expect(phaseLabel("mystery", t)).toBe("mystery");
    expect(phaseStatusLabel("mystery", t)).toBe("mystery");
    expect(keys).toEqual([
      "teamRuns.phaseName.mystery",
      "teamRuns.phaseStatus.mystery",
    ]);
  });

  it("an unknown status still renders visible text instead of an empty tag", () => {
    render(
      <PhaseStepper
        phases={[phase("deliver", 8, "mystery")]}
        pendingDecision={null}
      />,
    );

    expect(screen.getByTestId("phase-status-deliver").textContent).toBe(
      "mystery",
    );
    expect(
      screen.getByTestId("phase-deliver").getAttribute("data-status"),
    ).toBe("mystery");
  });
});
