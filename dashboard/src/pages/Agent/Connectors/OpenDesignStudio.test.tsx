import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { App } from "antd";
import { beforeEach, expect, it, vi } from "vitest";
import { OpenDesignStudio } from "./OpenDesignStudio";
import { openDesignApi } from "../../../api/modules/openDesign";
vi.mock("../../../api/modules/openDesign", () => ({
  openDesignApi: { catalog: vi.fn(), resource: vi.fn() },
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("./OpenDesignHealth", () => ({ OpenDesignHealth: () => null }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(openDesignApi.catalog).mockResolvedValue({
    resources: [{ uri: "od://skills/test/SKILL.md", name: "Test material" }],
    agents: [],
    next_cursor: null,
    selection: { skills: [] },
  });
});

it("opens material contents in a separate modal and keeps the catalog open", async () => {
  vi.mocked(openDesignApi.resource).mockResolvedValue({
    uri: "od://skills/test/SKILL.md",
    text: "<script>untrusted text</script>",
    truncated: true,
  });
  render(
    <App>
      <OpenDesignStudio instanceId="i" />
    </App>,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "openDesignStudio.title" }),
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "openDesignStudio.read" }),
  );
  const modal = await waitFor(() => {
    // Ant Design's test-mode IDs are shared by the Drawer and Modal.
    const dialog = screen
      .getAllByRole("dialog")
      .find((node) => node.classList.contains("ant-modal"));
    expect(dialog).toBeDefined();
    return dialog!;
  });
  expect(
    await within(modal).findByText("<script>untrusted text</script>"),
  ).toBeInTheDocument();
  expect(
    within(modal).getByText("openDesignStudio.truncated"),
  ).toBeInTheDocument();
  expect(modal.querySelector("script")).toBeNull();
  expect(screen.getAllByRole("dialog")).toHaveLength(2);
  expect(
    screen.queryByText("openDesignStudio.pluginTitle"),
  ).not.toBeInTheDocument();
});

it("does not reopen a dismissed preview when its read finishes", async () => {
  let finish!: (value: {
    uri: string;
    text: string;
    truncated: boolean;
  }) => void;
  vi.mocked(openDesignApi.resource).mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  render(
    <App>
      <OpenDesignStudio instanceId="i" />
    </App>,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "openDesignStudio.title" }),
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "openDesignStudio.read" }),
  );
  const modal = await waitFor(() => {
    // Ant Design's test-mode IDs are shared by the Drawer and Modal.
    const dialog = screen
      .getAllByRole("dialog")
      .find((node) => node.classList.contains("ant-modal"));
    expect(dialog).toBeDefined();
    return dialog!;
  });
  fireEvent.click(within(modal).getByRole("button", { name: "Close" }));
  finish({
    uri: "od://skills/test/SKILL.md",
    text: "late result",
    truncated: false,
  });
  await waitFor(() => expect(modal).not.toBeVisible());
  expect(screen.queryByText("late result")).not.toBeInTheDocument();
});
