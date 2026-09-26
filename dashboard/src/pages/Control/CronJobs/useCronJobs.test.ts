import { describe, expect, it } from "vitest";
import {
  toOctopPatchBody,
  type CronJobFormValues,
} from "./useCronJobs";

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
  it("only includes fields that changed", () => {
    expect(
      toOctopPatchBody(
        { ...baseValues, name: "Renamed summary" },
        baseValues,
      ),
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
});
