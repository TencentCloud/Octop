import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

// UsersListPanel's import graph reaches react-pdf, which needs DOMMatrix.
vi.mock("react-pdf", () => ({
  Document: () => null,
  Page: () => null,
  pdfjs: { GlobalWorkerOptions: {} },
}));

import { Form } from "antd";
import { preferencesApi } from "../../../api/modules/preferences";
import {
  CollapsiblePermissionsField,
  PermissionCheckboxPicker,
  type PermissionCatalogItem,
} from "./UsersListPanel";

vi.mock("../../../api/modules/preferences", () => ({
  preferencesApi: {
    get: vi.fn(),
  },
}));

const CATALOG: PermissionCatalogItem[] = [
  { key: "experts", category: "nav", label: "Experts" },
  { key: "channels", category: "nav", label: "Channels" },
  { key: "terminal", category: "nav", label: "Terminal" },
  { key: "browser", category: "nav", label: "Browser" },
];

describe("PermissionCheckboxPicker", () => {
  beforeEach(() => {
    vi.mocked(preferencesApi.get).mockResolvedValue({
      sidebar_nav: null,
    } as never);
  });

  it("collapses a group and a page without changing the selection", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <PermissionCheckboxPicker
        catalog={CATALOG}
        value={["channels"]}
        onChange={onChange}
      />,
    );

    expect(
      await screen.findByRole("button", { name: "Channels" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "nav.settings" }),
    ).toHaveAttribute("aria-expanded", "true");

    await user.click(screen.getByRole("button", { name: "nav.settings" }));
    expect(screen.queryByRole("button", { name: "Channels" })).toBeNull();
    expect(screen.getByRole("button", { name: "Experts" })).toBeTruthy();
    expect(onChange).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "nav.settings" }));
    expect(screen.getByRole("button", { name: "Channels" })).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "nav.workbench" }));
    expect(screen.queryByRole("button", { name: "Terminal" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Browser" })).toBeNull();
    expect(screen.getByRole("button", { name: "Channels" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "nav.workbench" }),
    ).toHaveAttribute("aria-expanded", "false");

    await user.click(screen.getByRole("checkbox", { name: "nav.control" }));
    expect(onChange).toHaveBeenCalledWith(["channels", "terminal", "browser"]);
  });

  it("selects every permission in a folded page from its checkbox", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<PermissionCheckboxPicker catalog={CATALOG} onChange={onChange} />);

    await screen.findByRole("button", { name: "nav.workbench" });
    await user.click(screen.getByRole("button", { name: "nav.workbench" }));
    await user.click(screen.getByRole("checkbox", { name: "nav.workbench" }));

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(["terminal", "browser"]);
    });
    expect(screen.queryByRole("button", { name: "Terminal" })).toBeNull();
  });
});

describe("CollapsiblePermissionsField", () => {
  beforeEach(() => {
    vi.mocked(preferencesApi.get).mockResolvedValue({
      sidebar_nav: null,
    } as never);
  });

  it("stays collapsed until opened and still submits inherited permissions", async () => {
    const user = userEvent.setup();
    const onFinish = vi.fn();
    render(
      <Form initialValues={{ permissions: ["channels"] }} onFinish={onFinish}>
        <CollapsiblePermissionsField catalog={CATALOG} />
        <button type="submit">save</button>
      </Form>,
    );

    const toggle = screen.getByRole("button", {
      name: "adminUsers.colPermissions",
    });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "Channels" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "save" }));
    await waitFor(() => {
      expect(onFinish).toHaveBeenCalledWith(
        expect.objectContaining({ permissions: ["channels"] }),
      );
    });

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(
      await screen.findByRole("button", { name: "Channels" }),
    ).toBeTruthy();
  });
});
