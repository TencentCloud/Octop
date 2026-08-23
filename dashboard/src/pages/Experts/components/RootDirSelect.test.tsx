import { beforeEach, describe, expect, it, vi } from "vitest";
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

function openDropdown() {
  fireEvent.mouseDown(screen.getByRole("combobox"));
  return document.querySelector(".ant-select-dropdown") as HTMLElement;
}

/** Action buttons are hover-only; reveal them before clicking. */
function hoverTreeNode(dropdown: HTMLElement, text: string) {
  const node = Array.from(
    dropdown.querySelectorAll(".ant-select-tree-treenode"),
  ).find((n) => n.textContent?.includes(text));
  expect(node).toBeTruthy();
  fireEvent.mouseEnter(node!);
  return node as HTMLElement;
}

describe("<RootDirSelect /> mkdir + rename", () => {
  beforeEach(() => {
    mockedRequest.mockReset();
  });

  it("creates a folder under the clicked parent and enters rename mode without selecting it", async () => {
    const onChange = vi.fn();
    mockedRequest.mockImplementation(async (path, init) => {
      if (String(path).startsWith("/filesystem/dirs")) {
        return { entries: [] };
      }
      if (path === "/filesystem/mkdir" && init?.method === "POST") {
        return { path: "/New Folder", name: "New Folder" };
      }
      throw new Error(`unexpected request: ${String(path)}`);
    });

    render(
      <I18nextProvider i18n={i18n}>
        <RootDirSelect value="/" onChange={onChange} />
      </I18nextProvider>,
    );

    const dropdown = openDropdown();
    expect(dropdown).toBeTruthy();
    hoverTreeNode(dropdown, "/");
    const mkdirBtn = within(dropdown).getByTestId("root-dir-mkdir-/");
    fireEvent.click(mkdirBtn);

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith(
        "/filesystem/mkdir",
        expect.objectContaining({ method: "POST" }),
      );
    });

    expect(
      await within(dropdown).findByTestId("root-dir-rename-input"),
    ).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("prefers selected home path and still lists sibling dirs under /", async () => {
    const onChange = vi.fn();
    mockedRequest.mockImplementation(async (path) => {
      const p = String(path);
      if (p.startsWith("/filesystem/dirs")) {
        const listed = decodeURIComponent(p.split("path=")[1] ?? "");
        if (listed === "/") {
          return {
            entries: [
              { path: "/home", name: "home" },
              { path: "/tmp", name: "tmp" },
              { path: "/var", name: "var" },
            ],
          };
        }
        if (listed === "/home") {
          return {
            entries: [{ path: "/home/wally", name: "wally" }],
          };
        }
        return { entries: [] };
      }
      throw new Error(`unexpected request: ${String(path)}`);
    });

    render(
      <I18nextProvider i18n={i18n}>
        <RootDirSelect value="/home/wally" onChange={onChange} />
      </I18nextProvider>,
    );

    fireEvent.mouseDown(screen.getByRole("combobox"));
    const dropdown = document.querySelector(
      ".ant-select-dropdown",
    ) as HTMLElement;

    await waitFor(() => within(dropdown).getByText("wally"));
    await waitFor(() => within(dropdown).getByText("tmp"));
    expect(within(dropdown).getByText("var")).toBeInTheDocument();
    expect(within(dropdown).getByText("home")).toBeInTheDocument();
  });

  it("creates a nested folder, keeps a single tree under /, and shows rename input", async () => {
    const onChange = vi.fn();
    mockedRequest.mockImplementation(async (path, init) => {
      const p = String(path);
      if (p.startsWith("/filesystem/dirs")) {
        const listed = decodeURIComponent(p.split("path=")[1] ?? "");
        if (listed === "/") {
          return { entries: [{ path: "/Users", name: "Users" }] };
        }
        if (listed === "/Users") {
          return {
            entries: [{ path: "/Users/jubaoliang", name: "jubaoliang" }],
          };
        }
        return { entries: [] };
      }
      if (path === "/filesystem/mkdir" && init?.method === "POST") {
        return {
          path: "/Users/jubaoliang/新建文件夹",
          name: "新建文件夹",
        };
      }
      throw new Error(`unexpected request: ${String(path)}`);
    });

    render(
      <I18nextProvider i18n={i18n}>
        <RootDirSelect value="/Users/jubaoliang" onChange={onChange} />
      </I18nextProvider>,
    );

    fireEvent.mouseDown(screen.getByRole("combobox"));
    const dropdown = document.querySelector(
      ".ant-select-dropdown",
    ) as HTMLElement;

    // Selected value and siblings come from ancestor prefetch (API only).
    await waitFor(() => within(dropdown).getByText("jubaoliang"));
    expect(within(dropdown).getByText("Users")).toBeInTheDocument();

    hoverTreeNode(dropdown, "jubaoliang");
    fireEvent.click(
      within(dropdown).getByTestId("root-dir-mkdir-/Users/jubaoliang"),
    );

    await waitFor(() => {
      expect(mockedRequest).toHaveBeenCalledWith(
        "/filesystem/mkdir",
        expect.objectContaining({ method: "POST" }),
      );
    });

    expect(
      await within(dropdown).findByTestId("root-dir-rename-input"),
    ).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();

    // No root-level duplicate titled with the absolute path.
    const rootLevelTitles = Array.from(
      dropdown.querySelectorAll(".ant-select-tree-treenode"),
    )
      .filter(
        (n) => n.querySelectorAll(".ant-select-tree-indent-unit").length === 0,
      )
      .map((n) => n.textContent ?? "");
    expect(
      rootLevelTitles.some((text) =>
        text.includes("/Users/jubaoliang/新建文件夹"),
      ),
    ).toBe(false);
  });

  it("shows a rename button that enters inline rename without selecting the node", async () => {
    const onChange = vi.fn();
    mockedRequest.mockImplementation(async (path) => {
      const p = String(path);
      if (p.startsWith("/filesystem/dirs")) {
        const listed = decodeURIComponent(p.split("path=")[1] ?? "");
        if (listed === "/") {
          return { entries: [{ path: "/Users", name: "Users" }] };
        }
        return { entries: [] };
      }
      throw new Error(`unexpected request: ${String(path)}`);
    });

    render(
      <I18nextProvider i18n={i18n}>
        <RootDirSelect value="/" onChange={onChange} />
      </I18nextProvider>,
    );

    const dropdown = openDropdown();
    fireEvent.click(dropdown.querySelector(".ant-select-tree-switcher")!);
    await waitFor(() => within(dropdown).getByText("Users"));

    hoverTreeNode(dropdown, "Users");
    fireEvent.click(within(dropdown).getByTestId("root-dir-rename-/Users"));

    expect(
      await within(dropdown).findByTestId("root-dir-rename-input"),
    ).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
    // Root itself has no rename button.
    expect(within(dropdown).queryByTestId("root-dir-rename-/")).toBeNull();
  });

  it("shows the full absolute path in the closed selector", () => {
    mockedRequest.mockResolvedValue({ entries: [] });

    const { container } = render(
      <I18nextProvider i18n={i18n}>
        <RootDirSelect value="/Users/jubaoliang/workspace" />
      </I18nextProvider>,
    );

    const item = container.querySelector(".ant-select-selection-item");
    expect(item).toHaveTextContent("/Users/jubaoliang/workspace");
  });

  it("does not show mkdir/rename buttons in the closed selector", () => {
    mockedRequest.mockResolvedValue({ entries: [] });

    const { container } = render(
      <I18nextProvider i18n={i18n}>
        <RootDirSelect value="/" />
      </I18nextProvider>,
    );

    const selector = container.querySelector(".ant-select-selector");
    expect(selector).toBeTruthy();
    expect(
      selector!.querySelector('[data-testid="root-dir-mkdir-/"]'),
    ).toBeNull();
  });

  it("does not show mkdir buttons in the input while the dropdown is open", async () => {
    mockedRequest.mockImplementation(async (path) => {
      if (String(path).startsWith("/filesystem/dirs")) {
        return { entries: [{ path: "/Users", name: "Users" }] };
      }
      throw new Error(`unexpected request: ${String(path)}`);
    });

    const { container } = render(
      <I18nextProvider i18n={i18n}>
        <RootDirSelect value="/" />
      </I18nextProvider>,
    );

    const dropdown = openDropdown();
    fireEvent.click(dropdown.querySelector(".ant-select-tree-switcher")!);
    await waitFor(() => within(dropdown).getByText("Users"));

    // Actions stay in the tree dropdown…
    expect(
      within(dropdown).getByTestId("root-dir-mkdir-/"),
    ).toBeInTheDocument();
    // …but never in the input chrome (treeNodeLabelProp=value, no treeTitleRender).
    const selector = container.querySelector(".ant-select-selector");
    expect(selector).toBeTruthy();
    expect(
      selector!.querySelector('[data-testid="root-dir-mkdir-/"]'),
    ).toBeNull();
    expect(selector!.querySelector("[data-root-dir-actions]")).toBeNull();
  });
});
