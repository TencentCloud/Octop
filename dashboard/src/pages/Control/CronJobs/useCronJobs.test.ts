import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  toOctopPatchBody,
  useCronJobs,
  type CronJobFormValues,
} from "./useCronJobs";

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  patch: vi.fn(),
  settings: vi.fn(),
  t: (key: string) => key,
}));

vi.mock("../../../context/AgentContext", () => ({
  useAgent: () => ({
    activeAgentId: "agent-1",
    activeAgent: { is_owner: true },
  }),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: mocks.t }) }));
vi.mock("../../../api/modules/cronjob", () => ({ octopCronApi: mocks }));
vi.mock("@/utils/antdMessage", () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

const baseValues: CronJobFormValues = {
  name: "Daily summary",
  enabled: true,
  schedule: {
    type: "cron",
    cron: "0 9 * * *",
    timezone: "UTC",
  },
  _scheduleMode: "custom",
  prompt: "Summarize recent activity",
  task_type: "agent",
  model: "openai/gpt-5",
  fresh_thread: false,
  session_key: "agent:dashboard:1:dm",
  mcp_servers: ["github"],
};

describe("toOctopPatchBody", () => {
  it("does not resend unchanged fields", () => {
    expect(
      toOctopPatchBody({ ...baseValues, mcp_servers: ["github"] }, baseValues),
    ).toEqual({});
  });

  it("only includes fields that changed", () => {
    expect(
      toOctopPatchBody({ ...baseValues, name: "Renamed summary" }, baseValues),
    ).toEqual({ name: "Renamed summary" });
  });

  it("keeps explicit model and MCP changes in the patch", () => {
    expect(
      toOctopPatchBody(
        {
          ...baseValues,
          model: undefined,
          mcp_servers: [],
        },
        baseValues,
      ),
    ).toEqual({
      model: null,
      mcp_servers: [],
    });
  });

  it("changes the schedule without resending model, MCP, or session", () => {
    expect(
      toOctopPatchBody(
        {
          ...baseValues,
          schedule: { ...baseValues.schedule, cron: "0 10 * * *" },
        },
        baseValues,
      ),
    ).toEqual({ trigger: "cron:0 10 * * *" });
  });
});

describe("useCronJobs updateJob", () => {
  it("sends only the edited name and keeps existing model and MCP settings", async () => {
    const row = {
      id: "job-1",
      agent_id: "agent-1",
      name: baseValues.name,
      prompt: baseValues.prompt,
      trigger: "cron:0 9 * * *",
      task_type: baseValues.task_type,
      enabled: true,
      model: baseValues.model,
      mcp_servers: baseValues.mcp_servers,
      fresh_thread: false,
      session_key: baseValues.session_key,
    };
    mocks.settings.mockResolvedValue({ timezone: "UTC" });
    mocks.list.mockResolvedValue([row]);
    mocks.patch.mockResolvedValue({ ...row, name: "Renamed summary" });

    const { result } = renderHook(() => useCronJobs());
    await waitFor(() => expect(result.current.jobs).toHaveLength(1));
    const values = result.current.jobToFormValues(
      result.current.jobs[0],
      "UTC",
    );
    await act(async () => {
      expect(
        await result.current.updateJob("job-1", {
          ...values,
          name: "Renamed summary",
        }),
      ).toBe(true);
    });
    expect(mocks.patch).toHaveBeenCalledWith("agent-1", "job-1", {
      name: "Renamed summary",
    });
  });
});
