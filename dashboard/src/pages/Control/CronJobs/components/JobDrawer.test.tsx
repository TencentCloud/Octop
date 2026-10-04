import { Form } from "antd";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { JobDrawer } from "./JobDrawer";
import type { CronJobFormValues } from "../useCronJobs";
const variant = vi.hoisted(() => ({ enabled: true }));
vi.mock("../../../../workbuddy/variant", () => ({
  get WORKBUDDY_UI() {
    return variant.enabled;
  },
}));
vi.mock("../../../../api/modules/provider", () => ({
  providerApi: { listResolvedModels: vi.fn().mockResolvedValue([]) },
}));
vi.mock("../../../../api/modules/connectors", () => ({
  connectorsApi: { listInstances: vi.fn().mockResolvedValue([]) },
}));
function Editor({ submit }: { submit: (values: CronJobFormValues) => void }) {
  const [form] = Form.useForm<CronJobFormValues>();
  return (
    <JobDrawer
      open
      editingJob={null}
      activeAgentId={null}
      cronTimezone="Asia/Shanghai"
      form={form}
      onClose={() => {}}
      onSubmit={submit}
    />
  );
}
describe("automation editor actions", () => {
  it.each([true, false])(
    "validates and submits the existing form with WorkBuddy=%s",
    async (workbuddy) => {
      variant.enabled = workbuddy;
      const submit = vi.fn();
      render(<Editor submit={submit} />);
      const save = screen.getByRole("button", { name: "common.save" });
      expect(Boolean(save.closest(".ant-modal-footer"))).toBe(workbuddy);
      await userEvent.click(save);
      expect(submit).not.toHaveBeenCalled();
      await userEvent.type(
        screen.getByPlaceholderText("cronJobs.jobNamePlaceholder"),
        "Audit task",
      );
      await userEvent.type(
        screen.getByPlaceholderText("cronJobs.form.agentPromptPlaceholder"),
        "Test instruction",
      );
      await userEvent.click(save);
      await waitFor(() => expect(submit).toHaveBeenCalledOnce());
      expect(submit.mock.calls[0][0]).toMatchObject({
        name: "Audit task",
        prompt: "Test instruction",
        schedule: { timezone: "Asia/Shanghai" },
      });
    },
  );
});
