import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// Only the transport is mocked: both pages must go through ``projectsApi`` /
// ``projectMetadataApi``, so asserting on ``request`` proves the real paths and
// request bodies (R4 field set, PLAN §6.3 wrapper reuse).
vi.mock("../../api/request", () => ({
  request: vi.fn(),
  requestBlob: vi.fn(),
  requestUpload: vi.fn(),
}));

vi.mock("@/utils/antdMessage", () => ({
  message: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

// The shared setup mock hands out a *fresh* ``t`` on every render, which turns
// ``Detail/index.tsx``'s ``useCallback(load, [projectId, t])`` + ``useEffect``
// into an endless refetch loop ("Maximum update depth exceeded"). Real i18next
// keeps ``t`` stable, so this file pins a stable one and keeps ``t(key)`` →
// key so assertions stay on the frozen key names.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: unknown): string =>
    typeof fallback === "string" ? fallback : key;
  return {
    useTranslation: () => ({
      t,
      i18n: { language: "zh", changeLanguage: () => Promise.resolve() },
    }),
    Trans: ({ children }: { children?: unknown }) => children,
  };
});

import { request } from "../../api/request";
import zh from "../../locales/zh.json";
import type { ProjectOut } from "../../api/modules/projects";
import ProjectsPage from "./index";
import ProjectDetailPage from "./Detail/index";

const mockedRequest = vi.mocked(request);

const PROJECT: ProjectOut = {
  project_id: "p1",
  name: "Website revamp",
  goal: "Ship v2",
  status: "cancelled",
  owner_user_id: 7,
  memory_namespace: "project-p1",
  kb_id: null,
  start_at: null,
  due_at: null,
  created_at: 1700000000,
  updated_at: 1700000000,
};

type Handler = (init?: RequestInit) => unknown;

let routes: Record<string, Handler>;

function callFor(method: string, path: string): [string, RequestInit] {
  const found = mockedRequest.mock.calls.find(
    ([called, init]) => called === path && (init?.method ?? "GET") === method,
  );
  expect(found, `${method} ${path} was never requested`).toBeTruthy();
  return found as [string, RequestInit];
}

function bodyOf(init: RequestInit): Record<string, unknown> {
  return JSON.parse(String(init.body)) as Record<string, unknown>;
}

function renderRoutes(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function openCreateDialog() {
  renderRoutes("/projects");
  await waitFor(() => {
    expect(screen.getByText("Website revamp")).toBeInTheDocument();
  });
  fireEvent.click(screen.getByRole("button", { name: "projects.create" }));
  return screen.findByTestId("create-project-dialog");
}

beforeEach(() => {
  vi.clearAllMocks();
  routes = {
    "GET /settings/timezone": () => ({ timezone: "UTC" }),
    "GET /projects": () => [PROJECT],
    "POST /projects": () => PROJECT,
    "GET /projects/p1": () => PROJECT,
    "GET /projects/p1/members": () => [],
    "GET /projects/p1/tasks": () => [],
    "GET /projects/p1/tags": () => [],
    "GET /projects/p1/custom-fields": () => [],
  };
  mockedRequest.mockImplementation(
    async (path: string, init?: RequestInit): Promise<unknown> => {
      const method = init?.method ?? "GET";
      const handler = routes[`${method} ${path}`];
      if (!handler) throw new Error(`unexpected request: ${method} ${path}`);
      return handler(init);
    },
  );
});

describe("new-project dialog (R4 interaction alignment)", () => {
  it("shows the breadcrumb, inline title, description and chip toolbar", async () => {
    const dialog = await openCreateDialog();

    // The breadcrumb is the modal header (it also names the dialog).
    const breadcrumb = screen.getByTestId("create-project-breadcrumb");
    expect(breadcrumb.textContent).toContain("projects.title");
    expect(breadcrumb.textContent).toContain("projects.create");

    expect(
      within(dialog).getByTestId("create-project-name"),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByTestId("create-project-goal"),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "projects.chipStatus" }),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "projects.chipStartAt" }),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "projects.chipDueAt" }),
    ).toBeInTheDocument();
  });

  it("exposes exactly the five frozen fields and nothing else", async () => {
    const dialog = await openCreateDialog();

    const fields = Array.from(
      dialog.querySelectorAll('[data-testid^="create-project-field-"]'),
    ).map((node) => node.getAttribute("data-testid"));
    expect(fields).toEqual([
      "create-project-field-name",
      "create-project-field-goal",
      "create-project-field-status",
      "create-project-field-start",
      "create-project-field-due",
    ]);

    // R4 forbids priority / assignee / repository here. The repository field
    // has no key at all in the frozen table, so it cannot be rendered.
    for (const forbidden of [
      "projects.chipPriority",
      "projects.chipAssignee",
    ]) {
      expect(
        within(dialog).queryByRole("button", { name: forbidden }),
      ).not.toBeInTheDocument();
    }
  });

  it("submits the five aligned fields and never the three forbidden ones", async () => {
    const dialog = await openCreateDialog();

    fireEvent.change(within(dialog).getByTestId("create-project-name"), {
      target: { value: "Website revamp" },
    });
    fireEvent.change(within(dialog).getByTestId("create-project-goal"), {
      target: { value: "Ship v2" },
    });
    // Drive the status chip's popover.
    fireEvent.click(
      within(dialog).getByRole("button", { name: "projects.chipStatus" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "projects.statusCancelled" }),
    );

    fireEvent.click(
      within(dialog.closest(".ant-modal") as HTMLElement).getByRole("button", {
        name: "common.create",
      }),
    );

    await waitFor(() => {
      expect(callFor("POST", "/projects")).toBeTruthy();
    });
    const body = bodyOf(callFor("POST", "/projects")[1]);
    expect(Object.keys(body).sort()).toEqual([
      "due_at",
      "goal",
      "name",
      "start_at",
      "status",
    ]);
    expect(body).toEqual({
      name: "Website revamp",
      goal: "Ship v2",
      status: "cancelled",
      start_at: null,
      due_at: null,
    });
  });

  it("offers six distinct status options and warns when archived is picked", async () => {
    const dialog = await openCreateDialog();

    fireEvent.click(
      within(dialog).getByRole("button", { name: "projects.chipStatus" }),
    );
    const menu = document.querySelector(".ant-popover") as HTMLElement;
    expect(menu).toBeTruthy();

    const optionTexts = Array.from(menu.querySelectorAll("button")).map(
      (node) => node.textContent,
    );
    expect(optionTexts).toHaveLength(6);
    expect(new Set(optionTexts).size).toBe(6);
    expect(
      within(menu).getByRole("button", { name: "projects.statusArchived" }),
    ).toBeInTheDocument();
    expect(
      within(menu).getByRole("button", { name: "projects.statusCancelled" }),
    ).toBeInTheDocument();

    // S-10: picking ``archived`` must surface the read-only hint.
    expect(
      within(dialog).queryByTestId("create-project-archived-hint"),
    ).not.toBeInTheDocument();
    fireEvent.click(
      within(menu).getByRole("button", { name: "projects.statusArchived" }),
    );
    expect(
      await within(dialog).findByTestId("create-project-archived-hint"),
    ).toHaveTextContent("projects.archiveConfirmDesc");
  });

  it("reopens with a clean field set", async () => {
    const dialog = await openCreateDialog();
    fireEvent.change(within(dialog).getByTestId("create-project-name"), {
      target: { value: "Draft name" },
    });
    expect(within(dialog).getByTestId("create-project-name")).toHaveValue(
      "Draft name",
    );

    fireEvent.click(
      within(dialog.closest(".ant-modal") as HTMLElement).getByRole("button", {
        name: "common.cancel",
      }),
    );
    await waitFor(() => {
      expect(screen.queryByTestId("create-project-dialog")).toBeNull();
    });

    fireEvent.click(screen.getByRole("button", { name: "projects.create" }));
    const reopened = await screen.findByTestId("create-project-dialog");
    expect(within(reopened).getByTestId("create-project-name")).toHaveValue("");
  });
});

describe("project status copy (AC-U-22 / AC-U-23)", () => {
  it("keeps all six zh values distinct — archived is not cancelled", () => {
    const copy = zh.projects as Record<string, string>;
    const keys = [
      "statusDraft",
      "statusActive",
      "statusPaused",
      "statusCompleted",
      "statusCancelled",
      "statusArchived",
    ];
    const values = keys.map((key) => copy[key]);
    for (const value of values) {
      expect(value).toBeTruthy();
    }
    expect(new Set(values).size).toBe(6);
    expect(copy.statusCancelled).not.toBe(copy.statusArchived);
  });

  it("renders the new status labels on the detail page", async () => {
    renderRoutes("/projects/p1");

    const statusTag = await screen.findByText("projects.statusCancelled");
    expect(statusTag).toBeInTheDocument();
  });
});

describe("project detail metadata mount (T-FE-META products)", () => {
  it("mounts the tag and custom-field definition panels", async () => {
    renderRoutes("/projects/p1");

    expect(await screen.findByTestId("project-tags")).toBeInTheDocument();
    expect(
      await screen.findByTestId("project-custom-fields"),
    ).toBeInTheDocument();
    // The read rings really ran (empty project → the panels' empty states).
    await waitFor(() => {
      expect(callFor("GET", "/projects/p1/tags")).toBeTruthy();
      expect(callFor("GET", "/projects/p1/custom-fields")).toBeTruthy();
    });
    expect(screen.getByText("projects.tagsEmpty")).toBeInTheDocument();
    expect(screen.getByText("projects.cfEmpty")).toBeInTheDocument();
  });
});
