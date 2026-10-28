import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { App } from "antd";
import KnowledgeBases from "./index";

const state = vi.hoisted(() => ({
  t: (key: string) => key,
  user: { id: 2, role: "user", permissions: ["knowledge_bases"] },
  bases: [] as Record<string, unknown>[],
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
  return {
    ...actual,
    knowledgeBasesApi: {
      list: vi.fn(async () => state.bases),
      getCapability: vi.fn(async () => ({
        usable: true,
        backend: "remote",
        ocr: {},
      })),
      get: vi.fn(async () => state.bases[0]),
      listDocuments: vi.fn(async () => []),
    },
  };
});

function view() {
  return (
    <MemoryRouter>
      <App>
        <KnowledgeBases />
      </App>
    </MemoryRouter>
  );
}

describe("knowledge creation permission", () => {
  beforeEach(() => {
    localStorage.clear();
    state.user = { id: 2, role: "user", permissions: ["knowledge_bases"] };
    state.bases = [];
  });

  it("hides creation on the empty guide when the user can only read", async () => {
    render(view());
    await screen.findByText("knowledgeBases.emptyGuideTitle");
    expect(
      screen.queryByRole("button", { name: "knowledgeBases.create" }),
    ).toBeNull();
  });

  it("keeps a shared base visible without showing list creation", async () => {
    state.bases = [
      { id: "kb", name: "Shared documents", owner_user_id: 1, doc_count: 0 },
    ];
    render(view());
    await screen.findByText("Shared documents");
    expect(
      screen.queryByRole("button", { name: "knowledgeBases.create" }),
    ).toBeNull();
  });

  it.each(["creator", "admin"])("allows %s to open creation", async (role) => {
    state.user = {
      id: 2,
      role: role === "admin" ? "admin" : "user",
      permissions:
        role === "admin" ? [] : ["knowledge_bases", "knowledge_bases:create"],
    };
    const user = userEvent.setup();
    render(view());
    const create = await screen.findByRole("button", {
      name: "knowledgeBases.create",
    });
    await user.click(create);
    await waitFor(() => expect(screen.getByRole("dialog")).toBeVisible());
  });

  it("closes a pending create form when permission is revoked", async () => {
    state.user.permissions = ["knowledge_bases", "knowledge_bases:create"];
    const user = userEvent.setup();
    const { rerender } = render(view());
    await user.click(
      await screen.findByRole("button", { name: "knowledgeBases.create" }),
    );
    await screen.findByRole("dialog");
    state.user.permissions = ["knowledge_bases"];
    rerender(view());
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});
