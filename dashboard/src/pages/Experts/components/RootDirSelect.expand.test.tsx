import { describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import i18n from "../../../i18n";

vi.mock("../../../api/request", () => ({
  request: vi.fn(),
}));

vi.mock("@/utils/antdMessage", () => ({
  message: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

import { request } from "../../../api/request";
import RootDirSelect from "./RootDirSelect";

const mockedRequest = vi.mocked(request);

describe("RootDirSelect expand nesting", () => {
  it("keeps loaded children indented under the expanded parent", async () => {
    mockedRequest.mockImplementation(async (path) => {
      const p = String(path);
      if (p.startsWith("/filesystem/dirs")) {
        const listed = decodeURIComponent(p.split("path=")[1] ?? "");
        if (listed === "/") {
          return {
            entries: [
              { path: "/Users", name: "Users" },
              { path: "/tmp", name: "tmp" },
            ],
          };
        }
        if (listed === "/Users") {
          return {
            entries: [{ path: "/Users/jubaoliang", name: "jubaoliang" }],
          };
        }
      }
      return { entries: [] };
    });

    render(
      <I18nextProvider i18n={i18n}>
        <RootDirSelect value="/" />
      </I18nextProvider>,
    );

    fireEvent.mouseDown(screen.getByRole("combobox"));
    const dropdown = document.querySelector(
      ".ant-select-dropdown",
    ) as HTMLElement;
    expect(dropdown).toBeTruthy();

    const rootSwitcher = dropdown.querySelector(".ant-select-tree-switcher");
    expect(rootSwitcher).toBeTruthy();
    fireEvent.click(rootSwitcher!);

    await waitFor(() => {
      expect(within(dropdown).getByText("Users")).toBeInTheDocument();
    });

    const usersSwitcher = Array.from(
      dropdown.querySelectorAll(".ant-select-tree-treenode"),
    )
      .find((n) => n.textContent?.includes("Users"))
      ?.querySelector(".ant-select-tree-switcher");
    expect(usersSwitcher).toBeTruthy();
    fireEvent.click(usersSwitcher!);

    await waitFor(() => {
      expect(within(dropdown).getByText("jubaoliang")).toBeInTheDocument();
    });

    const childNode = Array.from(
      dropdown.querySelectorAll(".ant-select-tree-treenode"),
    ).find((n) => n.textContent?.includes("jubaoliang"));

    const indentUnits =
      childNode?.querySelectorAll(".ant-select-tree-indent-unit").length ?? 0;

    expect(indentUnits).toBeGreaterThanOrEqual(2);
  });

  it("does not hoist children to root level after expand", async () => {
    mockedRequest.mockImplementation(async (path) => {
      const p = String(path);
      if (p.startsWith("/filesystem/dirs")) {
        const listed = decodeURIComponent(p.split("path=")[1] ?? "");
        if (listed === "/") {
          return {
            entries: [{ path: "/Users", name: "Users" }],
          };
        }
        if (listed === "/Users") {
          return {
            entries: [
              { path: "/Users/a", name: "a" },
              { path: "/Users/b", name: "b" },
            ],
          };
        }
      }
      return { entries: [] };
    });

    render(
      <I18nextProvider i18n={i18n}>
        <RootDirSelect value="/" />
      </I18nextProvider>,
    );

    fireEvent.mouseDown(screen.getByRole("combobox"));
    const dropdown = document.querySelector(
      ".ant-select-dropdown",
    ) as HTMLElement;

    fireEvent.click(dropdown.querySelector(".ant-select-tree-switcher")!);
    await waitFor(() => within(dropdown).getByText("Users"));

    const usersNode = Array.from(
      dropdown.querySelectorAll(".ant-select-tree-treenode"),
    ).find((n) => n.textContent?.includes("Users"));
    fireEvent.click(usersNode!.querySelector(".ant-select-tree-switcher")!);

    await waitFor(() => within(dropdown).getByText("a"));

    const treenodes = Array.from(
      dropdown.querySelectorAll(".ant-select-tree-treenode"),
    ).map((n) => ({
      text: n.textContent,
      level: n.querySelectorAll(".ant-select-tree-indent-unit").length,
    }));

    const rootLevel = treenodes.filter((n) => n.level === 0);
    expect(rootLevel.some((n) => n.text?.includes("a"))).toBe(false);
    expect(rootLevel.some((n) => n.text?.includes("b"))).toBe(false);

    const a = treenodes.find((n) => n.text?.includes("a"));
    const b = treenodes.find((n) => n.text?.includes("b"));
    expect(a?.level).toBe(2);
    expect(b?.level).toBe(2);
  });
});
