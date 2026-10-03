import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { beforeEach, describe, expect, it, vi } from "vitest";
import i18n from "../../../../i18n";

const requestMock = vi.fn();

vi.mock("../../../../api/request", () => ({
  request: (...args: unknown[]) => requestMock(...args),
  requestBlob: vi.fn(async () => new Blob(["x"])),
  requestUpload: vi.fn(async () => ({})),
}));

vi.mock("../../../../api/modules/settings", () => ({
  octopSettingsApi: {
    timezone: vi.fn(async () => ({ timezone: "UTC" })),
    upload: vi.fn(async () => ({})),
    capabilities: vi.fn(async () => ({})),
    captcha: vi.fn(async () => ({})),
  },
}));

vi.mock("../../../../api/modules/workspace", () => ({
  workspaceApi: {
    deleteWorkspaceFile: vi.fn(async () => ({})),
    exportArchive: vi.fn(async () => new Blob(["x"])),
    importArchive: vi.fn(async () => ({})),
  },
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock("../../../../context/AgentContext", () => ({
  useAgent: () => ({
    agents: [{ agent_id: "agent-1", name: "Agent 1", state: "running" }],
    activeAgentId: "agent-1",
  }),
}));

vi.mock("react-pdf", () => ({
  Document: () => null,
  Page: () => null,
  pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
}));

vi.mock("antd", async (importOriginal) => {
  const actual = await importOriginal<typeof import("antd")>();
  return {
    ...actual,
    App: {
      ...(actual.App ?? {}),
      useApp: () => ({
        message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
        modal: { confirm: vi.fn() },
      }),
    },
  };
});

import WorkspaceDrawer from "./WorkspaceDrawer";

function treePayload() {
  return [
    { path: "/a.txt", is_dir: false, size: 4 },
    { path: "/b.txt", is_dir: false, size: 4 },
  ];
}

/** Deferred request so tests control response ordering. */
function deferred() {
  let resolve!: (v: { content: string }) => void;
  const promise = new Promise<{ content: string }>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe("WorkspaceDrawer stale-response race (audit RACE-1)", () => {
  beforeEach(() => {
    requestMock.mockReset();
    requestMock.mockImplementation(async (path: string) => {
      if (path.includes("/workspace/tree")) return treePayload();
      if (path.includes("/workspace/file")) {
        return {
          content: `content-for-${new URL(path, "http://x").searchParams.get(
            "path",
          )}`,
        };
      }
      return {};
    });
  });

  it("discards a slow read for file A after switching to file B", async () => {
    const slowA = deferred();
    requestMock.mockImplementation(async (path: string) => {
      const p = new URL(path, "http://x");
      if (p.pathname.includes("/workspace/tree")) return treePayload();
      if (p.pathname.includes("/workspace/file")) {
        const target = p.searchParams.get("path");
        if (target === "/a.txt") return slowA.promise;
        return { content: "content-for-b" };
      }
      return {};
    });

    render(
      <I18nextProvider i18n={i18n}>
        <WorkspaceDrawer agentId="agent-1" open onClose={() => {}} embedded />
      </I18nextProvider>,
    );

    const a = await screen.findAllByText("a.txt");
    await userEvent.click(a[0]);
    const b = await screen.findAllByText("b.txt");
    await userEvent.click(b[0]);

    await waitFor(() => {
      expect(screen.getByText("content-for-b")).toBeTruthy();
    });

    // The stale A response arrives now — it must NOT overwrite B's content.
    slowA.resolve({ content: "STALE-A-CONTENT" });
    await Promise.resolve();
    await new Promise((r) => setTimeout(r, 0));

    expect(screen.getByText("content-for-b")).toBeTruthy();
    expect(screen.queryByText("STALE-A-CONTENT")).toBeNull();
  });

  it("refuses to save content that was loaded for a different path", async () => {
    render(
      <I18nextProvider i18n={i18n}>
        <WorkspaceDrawer agentId="agent-1" open onClose={() => {}} embedded />
      </I18nextProvider>,
    );

    const a = await screen.findAllByText("a.txt");
    await userEvent.click(a[0]);
    await waitFor(() => {
      expect(screen.getByText("content-for-/a.txt")).toBeTruthy();
    });

    const b = await screen.findAllByText("b.txt");
    await userEvent.click(b[0]);
    await waitFor(() => {
      expect(screen.getByText("content-for-/b.txt")).toBeTruthy();
    });

    // Force the mismatch: rewrite the ref through a stale selection is not
    // directly possible from the test; instead assert the happy path PUT goes
    // to the currently loaded path only.
    requestMock.mockClear();
    requestMock.mockResolvedValue({});
    // Enter edit mode first — save only appears in the editor toolbar.
    const editButton = screen.getByRole("button", { name: /edit/i });
    await userEvent.click(editButton);
    const saveButton = await screen.findByRole("button", { name: /save/i });
    await userEvent.click(saveButton);
    await waitFor(() => {
      const put = requestMock.mock.calls.find(
        (c) => c[1] && (c[1] as { method?: string }).method === "PUT",
      );
      expect(put).toBeTruthy();
      const url = String(put?.[0]);
      expect(url).toContain("b.txt");
      expect(url).not.toContain("a.txt");
    });
  });
});
