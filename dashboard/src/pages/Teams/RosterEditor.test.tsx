/**
 * T-34 acceptance: the room renders speakers with data-sourced roles, and the roster
 * page pins the host, shows cut roles, and never reaches the network by itself.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import RosterEditor, { isLeadMember, orderRoster } from "./RosterEditor";
import { TeamSpeakerRow } from "../Chat/components/MessageSender";
import type { TeamRoster } from "../../api/modules/teams";

const ROSTER: TeamRoster = {
  lead_agent_id: "a-backend",
  members: [
    { agent_id: "a-pm", role: "pm" },
    { agent_id: "a-backend", role: "backend" },
    { agent_id: "a-qa", role: null },
  ],
};

describe("room renders by speaker (T-34 ①)", () => {
  it("shows avatar + name + role tag, with the role taken from the roster data", () => {
    const { container } = render(
      <TeamSpeakerRow
        displayName="Eric"
        role="backend"
        isLead
        profileAgentId="a-backend"
        color="#123456"
      />,
    );
    // 三要素：头像（svg 容器）、名字、角色标签。
    expect(container.querySelector("svg")).toBeTruthy();
    expect(screen.getByTestId("team-speaker-name").textContent).toBe("Eric");
    expect(screen.getByTestId("team-speaker-role").textContent).toBe("backend");
    expect(screen.getByTestId("team-speaker-lead")).toBeTruthy();
  });

  it("keeps no role vocabulary of its own — the role is whatever the data says", () => {
    render(<TeamSpeakerRow displayName="Zoe" role="dba" />);
    expect(screen.getByTestId("team-speaker-role").textContent).toBe("dba");
    // 换一个数据里出现的角色，组件照样原样显示（说明它没有内置白名单）。
    render(<TeamSpeakerRow displayName="Ian" role="sec" />);
    expect(screen.getAllByTestId("team-speaker-role")[1].textContent).toBe(
      "sec",
    );
  });
});

describe("roster page (T-34 ②)", () => {
  it("pins the host to the top and tags it 队长/主持人", async () => {
    render(
      <RosterEditor
        teamId="t-1"
        load={async () => ROSTER}
        save={async () => ROSTER}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("roster-editor")).toBeTruthy(),
    );
    const rows = screen.getAllByTestId(/^roster-role-/);
    // 顺序：host 置顶（在 manifest 里它排第 2）。
    expect(rows[0].getAttribute("data-testid")).toBe("roster-role-a-backend");
    expect(screen.getByTestId("roster-lead-a-backend")).toBeTruthy();
    expect(screen.queryByTestId("roster-lead-a-pm")).toBeNull();
  });

  it("orderRoster/isLeadMember are pure functions over the data", () => {
    expect(orderRoster(ROSTER).map((m) => m.agent_id)).toEqual([
      "a-backend",
      "a-pm",
      "a-qa",
    ]);
    expect(
      orderRoster({ lead_agent_id: null, members: ROSTER.members })[0].agent_id,
    ).toBe("a-pm");
    expect(isLeadMember(ROSTER.members[1], "a-backend")).toBe(true);
    expect(isLeadMember(ROSTER.members[0], null)).toBe(false);
  });

  it("states 'host chairs it' when lead_agent_id is null instead of faking a lead", async () => {
    render(
      <RosterEditor
        teamId="t-2"
        load={async () => ({ lead_agent_id: null, members: ROSTER.members })}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("roster-host-chairs")).toBeTruthy(),
    );
    expect(screen.queryByTestId("roster-lead-a-backend")).toBeNull();
  });

  it("shows the cut roles (被裁可见、不静默丢弃)", async () => {
    render(
      <RosterEditor
        teamId="t-3"
        skippedRoles={["docs", "devops"]}
        load={async () => ROSTER}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("roster-skipped-roles")).toBeTruthy(),
    );
    expect(screen.getByTestId("roster-skipped-list").textContent).toContain(
      "docs / devops",
    );
  });

  it("opens a member's profile drawer when the caller wires it", async () => {
    const opened: string[] = [];
    render(
      <RosterEditor
        teamId="t-4"
        load={async () => ROSTER}
        onOpenProfile={(id) => opened.push(id)}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("roster-open-a-qa")).toBeTruthy(),
    );
    await userEvent.click(screen.getByTestId("roster-open-a-qa"));
    expect(opened).toEqual(["a-qa"]);
  });

  it("surfaces load errors instead of rendering an empty roster", async () => {
    render(
      <RosterEditor
        teamId="t-5"
        load={async () => {
          throw new Error("boom");
        }}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("roster-error")).toBeTruthy(),
    );
    expect(screen.queryByTestId("roster-editor")).toBeNull();
  });

  it("saves only when the explicit action is taken (no write on mount)", async () => {
    const save = vi.fn(async () => ROSTER);
    render(<RosterEditor teamId="t-6" load={async () => ROSTER} save={save} />);
    await waitFor(() => expect(screen.getByTestId("roster-save")).toBeTruthy());
    expect(save).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId("roster-save"));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    // 保存体里带的是**数据里的** lead，不是猜的。
    expect(save.mock.calls[0][1]).toMatchObject({ lead_agent_id: "a-backend" });
  });
});

describe("frontend boundary (T-34 ③/④)", () => {
  // 只扫**组件**（不扫本测试文件 —— 它自身含用于断言的模式串，会自证其罪）。
  const files = ["RosterEditor.tsx", "../Chat/components/MessageSender.tsx"];

  it("no component calls fetch/axios directly, and none imports TeamJobTracker", () => {
    const offenders: string[] = [];
    for (const file of files) {
      const source = readFileSync(join(__dirname, file), "utf8");
      for (const line of source.split("\n")) {
        const code = line.split("//")[0];
        if (/\bfetch\s*\(/.test(code) && !/readFileSync/.test(code))
          offenders.push(`${file}: fetch`);
        if (/\baxios\b/.test(code)) offenders.push(`${file}: axios`);
        // 只禁**导入**（R9 管的是数据来源）；文档里说明"不用它"是允许的，甚至应该被鼓励。
        if (
          /^\s*import\b.*TeamJobTracker|require\(.*TeamJobTracker/.test(code)
        ) {
          offenders.push(`${file}: TeamJobTracker import`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("the roster client is reused from api/ rather than re-implemented", () => {
    const source = readFileSync(join(__dirname, "RosterEditor.tsx"), "utf8");
    expect(source).toContain('from "../../api/modules/teams"');
    expect(source).toContain("getTeamRoster");
    expect(source).toContain("putTeamRoster");
  });
});
