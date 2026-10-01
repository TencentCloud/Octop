import { describe, expect, it } from "vitest";

import { buildDefaultFormValues, DEFAULT_FORM_VALUES } from "./constants";

describe("buildDefaultFormValues", () => {
  it("opens a new job on the agent task type", () => {
    expect(buildDefaultFormValues("UTC").task_type).toBe("agent");
  });

  it("keeps the create defaults in sync with DEFAULT_FORM_VALUES", () => {
    const built = buildDefaultFormValues("Asia/Shanghai");
    expect(built.task_type).toBe(DEFAULT_FORM_VALUES.task_type);
    expect(built.enabled).toBe(DEFAULT_FORM_VALUES.enabled);
    expect(built._preset).toBe(DEFAULT_FORM_VALUES._preset);
  });

  it("keeps the server-configured timezone and the blank prompt", () => {
    const built = buildDefaultFormValues("Europe/Berlin");
    expect(built.schedule).toEqual({ type: "cron", timezone: "Europe/Berlin" });
    expect(built.prompt).toBe("");
  });
});
