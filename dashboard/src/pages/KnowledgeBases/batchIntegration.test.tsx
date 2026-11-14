import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { App } from "antd";
import KnowledgeBases from "./index";

const state = vi.hoisted(() => ({
  t: (key: string, options?: { name?: string }) =>
    key === "knowledgeBases.batchSelectDocument"
      ? `Select ${options?.name}`
      : key,
  documents: [] as Record<string, unknown>[],
  user: { id: 2, role: "user", permissions: ["knowledge_bases"] },
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: state.t, i18n: { language: "en" } }),
}));
vi.mock("../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => state.user,
}));
vi.mock("../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "UTC",
}));
vi.mock("../../components/DocumentPreviewCore", () => ({
  default: () => null,
}));
vi.mock("../../api/modules/knowledgeBases", async (original) => {
  const actual = await original<
    typeof import("../../api/modules/knowledgeBases")
  >();
  const base = { id: "kb", name: "Documents", owner_user_id: 2, doc_count: 1 };
  return {
    ...actual,
    knowledgeBasesApi: {
      list: vi.fn(async () => [base]),
      get: vi.fn(async () => base),
      getCapability: vi.fn(async () => ({
        usable: true,
        backend: "remote",
        ocr: {},
      })),
      listDocuments: vi.fn(async () => state.documents),
    },
  };
});
function view(mode: "card" | "table") {
  localStorage.setItem("octop:knowledge-bases-docs-view", mode);
  return render(
    <MemoryRouter initialEntries={["/?kb=kb"]}>
      <App>
        <KnowledgeBases />
      </App>
    </MemoryRouter>,
  );
}
describe("batch selection with current knowledge document layouts", () => {
  beforeEach(() => {
    localStorage.clear();
    state.documents = [
      {
        id: "doc",
        filename: "report.md",
        path: "report.md",
        is_dir: false,
        byte_size: 42,
        chunk_count: 2,
        status: "ready",
        updated_at: 1,
      },
    ];
  });
  it("selects files in cards while retaining the current filename and action layout", async () => {
    const user = userEvent.setup();
    view("card");
    const checkbox = await screen.findByRole("checkbox", {
      name: "Select report.md",
    });
    expect(screen.getByText("report.md")).toBeVisible();
    await user.click(checkbox);
    expect(checkbox).toBeChecked();
    expect(
      screen.getByRole("button", { name: "knowledgeBases.batchReindex" }),
    ).toBeEnabled();
  });
  it("keeps chunk preview buttons available alongside table row selection", async () => {
    const user = userEvent.setup();
    view("table");
    expect(await screen.findByRole("button", { name: "2" })).toBeEnabled();
    const checkboxes = screen.getAllByRole("checkbox");
    await user.click(checkboxes[checkboxes.length - 1]);
    expect(
      screen.getByRole("button", { name: "knowledgeBases.batchReindex" }),
    ).toBeEnabled();
    expect(screen.getByRole("button", { name: "2" })).toBeEnabled();
  });
  it("retains the upstream upload guide for an empty writable base", async () => {
    state.documents = [];
    view("card");
    await waitFor(() =>
      expect(
        screen.getByText("knowledgeBases.emptyDocumentsTitle"),
      ).toBeVisible(),
    );
    for (const button of screen.getAllByRole("button", {
      name: "knowledgeBases.createFile",
    })) {
      expect(button).toBeEnabled();
    }
    expect(screen.queryByRole("checkbox")).toBeNull();
  });
});
