import { describe, expect, it } from "vitest";

import type { CronJobSpecOutput } from "../../../api/types";
import { buildDefaultFormValues } from "./components/constants";
import { jobToFormValues, toOctopCreateBody } from "./useCronJobs";

describe("cron form mapping", () => {
  it("keeps a script file job as script and sends the picked path", () => {
    const job = {
      id: "c1",
      name: "nightly",
      enabled: true,
      schedule: { type: "cron", cron: "0 9 * * *", timezone: "UTC" },
      task_type: "script",
      request: {
        input: [
          {
            role: "user",
            content: [{ type: "text", text: "scripts/nightly.py" }],
          },
        ],
      },
      meta: {
        octop_allow_all: true,
        octop_script_lang: "python",
        octop_script_source: "file",
        octop_script_path: "scripts/nightly.py",
        octop_model: "gpt-x",
        octop_mcp_servers: ["mail"],
      },
    } as CronJobSpecOutput;

    const values = jobToFormValues(job, "UTC");
    expect(values.task_type).toBe("script");
    expect(values.script_source).toBe("file");
    expect(values.script_path).toBe("scripts/nightly.py");

    const body = toOctopCreateBody({
      ...buildDefaultFormValues("UTC"),
      ...values,
      allow_all: true,
      model: "gpt-x",
      mcp_servers: ["mail"],
    });
    expect(body.task_type).toBe("script");
    expect(body.prompt).toBe("scripts/nightly.py");
    expect(body.script_path).toBe("scripts/nightly.py");
    expect(body.allow_all).toBe(false);
    expect(body.model).toBeNull();
    expect(body.mcp_servers).toEqual([]);
  });

  it("sends allow-all only for an agent job", () => {
    const agent = toOctopCreateBody({
      ...buildDefaultFormValues("UTC"),
      name: "digest",
      prompt: "summarize",
      task_type: "agent",
      allow_all: true,
    });
    expect(agent.allow_all).toBe(true);
    expect(agent.script_lang).toBeNull();

    const text = toOctopCreateBody({
      ...buildDefaultFormValues("UTC"),
      name: "water",
      prompt: "drink",
      task_type: "text",
      allow_all: true,
    });
    expect(text.allow_all).toBe(false);
  });
});
