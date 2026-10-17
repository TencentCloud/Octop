import { beforeEach, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import PluginPagesPage from "./index";
import {
  clearPluginPages,
  registerPluginPage,
  unregisterPluginPages,
} from "../../plugins/pages/registry";
import { pluginsApi } from "../../api/modules/plugins";
import { buildNavSections } from "../../layouts/sidebarNav";
import type { OctopUser } from "../../api/modules/auth";

vi.mock("../../api/modules/plugins", () => ({ pluginsApi: { list: vi.fn() } }));
vi.mock("../../plugins/toolRenderers/loader", () => ({
  loadInstalledPluginUis: vi.fn().mockResolvedValue(undefined),
}));
vi.mock("../../layouts/PageShell", () => ({
  default: ({
    title,
    children,
  }: {
    title: string;
    children: React.ReactNode;
  }) => (
    <section>
      <h1>{title}</h1>
      {children}
    </section>
  ),
}));
vi.mock("../../api/request", () => ({ request: vi.fn() }));
vi.mock("../../i18n", () => ({ default: { language: "en" } }));
vi.mock("../../pages/Chat/hooks/chatStore", () => ({
  patchToolResultData: vi.fn(),
}));

beforeEach(() => {
  clearPluginPages();
  vi.mocked(pluginsApi.list).mockResolvedValue([
    { id: "sample", enabled: true },
  ]);
});

function open(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/extensions" element={<PluginPagesPage />} />
        <Route
          path="/extensions/:pluginId/:pageId"
          element={<PluginPagesPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

it("lets a normal user discover and open a page with no agent, model or conversation", async () => {
  const normalUser = { role: "user", permissions: [] } as unknown as OctopUser;
  expect(
    buildNavSections(normalUser)
      .flatMap((section) => section.items)
      .some((item) => item.path === "/extensions"),
  ).toBe(true);
  registerPluginPage({
    pluginId: "sample",
    id: "welcome",
    title: "Welcome",
    component: () => <h2>Standalone welcome</h2>,
  });
  open("/extensions");
  fireEvent.click(await screen.findByRole("button", { name: "Open" }));
  expect(
    await screen.findByRole("heading", { name: "Standalone welcome" }),
  ).toBeInTheDocument();
});

it("shows an understandable unavailable state for an unknown page", async () => {
  open("/extensions/sample/unknown");
  expect(
    await screen.findByText("This plugin page is unavailable."),
  ).toBeInTheDocument();
});

it("removes an open page when its registry entry is removed", async () => {
  registerPluginPage({
    pluginId: "sample",
    id: "welcome",
    title: "Welcome",
    component: () => <h2>Standalone welcome</h2>,
  });
  open("/extensions/sample/welcome");
  expect(
    await screen.findByRole("heading", { name: "Standalone welcome" }),
  ).toBeInTheDocument();
  act(() => unregisterPluginPages("sample"));
  expect(
    await screen.findByText("This plugin page is unavailable."),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("heading", { name: "Standalone welcome" }),
  ).not.toBeInTheDocument();
});
