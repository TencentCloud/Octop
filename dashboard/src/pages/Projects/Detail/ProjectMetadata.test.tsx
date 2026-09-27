import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Only the transport is mocked: the panels must go through the shared
// ``projectMetadataApi`` wrapper, so asserting on ``request`` proves the
// frozen PLAN §4 / §6.3 paths *and* field names end to end.
vi.mock("../../../api/request", () => ({
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

// The confirm dialog itself is antd's; the panel's contract is "ask first with
// the cascade warning, then delete on OK" — captured by driving ``onOk``.
vi.mock("../../../utils/confirmModal", () => ({
  showConfirmModal: vi.fn(),
}));

import { request } from "../../../api/request";
import { showConfirmModal } from "../../../utils/confirmModal";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import type {
  ProjectCustomFieldDefinition,
  ProjectTagDefinition,
} from "../../../api/modules/projects";
import CustomFieldsPanel from "./CustomFieldsPanel";
import TagsManager from "./TagsManager";

const mockedRequest = vi.mocked(request);
const mockedConfirm = vi.mocked(showConfirmModal);

const PROJECT = "p1";

const DEFINITIONS: ProjectCustomFieldDefinition[] = [
  {
    field_id: "f1",
    key: "estimate",
    label: "Estimate",
    type: "number",
    required: true,
    options: [],
    sort_order: 0,
    created_at: 1700000000,
    updated_at: 1700000000,
  },
  {
    field_id: "f2",
    key: "stage",
    label: "Stage",
    type: "select",
    required: false,
    options: ["alpha", "beta"],
    sort_order: 1,
    created_at: 1700000100,
    updated_at: 1700000100,
  },
];

const TAGS: ProjectTagDefinition[] = [
  { tag_id: "t1", name: "urgent", color: "#ff0000", created_at: 1700000200 },
  { tag_id: "t2", name: "later", color: "", created_at: 1700000300 },
];

type Handler = (init?: RequestInit) => unknown;

let routes: Record<string, Handler>;

function bodyOf(init?: RequestInit): Record<string, unknown> {
  return init?.body
    ? (JSON.parse(String(init.body)) as Record<string, unknown>)
    : {};
}

/** The recorded call for one exact ``METHOD path`` pair. */
function callFor(method: string, path: string): [string, RequestInit] {
  const found = mockedRequest.mock.calls.find(
    ([called, init]) => called === path && (init?.method ?? "GET") === method,
  );
  expect(found, `${method} ${path} was never requested`).toBeTruthy();
  return found as [string, RequestInit];
}

async function findByLabel(scope: HTMLElement, label: string) {
  return waitFor(() => within(scope).getByLabelText(label));
}

beforeEach(() => {
  vi.clearAllMocks();
  routes = {
    "GET /settings/timezone": () => ({ timezone: "UTC" }),
    "GET /projects/p1/custom-fields": () => DEFINITIONS,
    "GET /projects/p1/tags": () => TAGS,
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

describe("CustomFieldsPanel", () => {
  it("lists definitions with type, required marker, options and a server-timezone date", async () => {
    render(<CustomFieldsPanel projectId={PROJECT} canEdit />);
    const section = await screen.findByTestId("project-custom-fields");

    await waitFor(() => {
      expect(within(section).getByText("Estimate")).toBeInTheDocument();
    });
    // Key, localized type label and the option set of the ``select`` definition.
    expect(within(section).getByText("estimate")).toBeInTheDocument();
    expect(within(section).getByText("stage")).toBeInTheDocument();
    expect(
      within(section).getByText("projects.cfTypeNumber"),
    ).toBeInTheDocument();
    expect(
      within(section).getByText("projects.cfTypeSelect"),
    ).toBeInTheDocument();
    expect(within(section).getByText("alpha")).toBeInTheDocument();
    expect(within(section).getByText("beta")).toBeInTheDocument();

    // Required marker: only the ``estimate`` row carries it.
    const rowTags = Array.from(
      section.querySelectorAll(".ant-table-tbody .ant-tag"),
    );
    const requiredMarkers = rowTags.filter(
      (tag) => tag.textContent === "projects.cfRequired",
    );
    expect(requiredMarkers).toHaveLength(1);
    // …and the ``select`` definition renders one tag per option.
    expect(rowTags.map((tag) => tag.textContent)).toEqual(
      expect.arrayContaining(["projects.cfRequired", "alpha", "beta"]),
    );

    // Dates always go through formatServerDateTime(epochSec, timeZone).
    expect(
      within(section).getByText(formatServerDateTime(1700000000, "UTC")),
    ).toBeInTheDocument();
  });

  it("renders an empty state instead of an empty control", async () => {
    routes["GET /projects/p1/custom-fields"] = () => [];
    render(<CustomFieldsPanel projectId={PROJECT} canEdit />);

    const empty = await screen.findByTestId("custom-fields-empty");
    expect(within(empty).getByText("projects.cfEmpty")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("creates a definition with the frozen request body", async () => {
    routes["POST /projects/p1/custom-fields"] = () => DEFINITIONS[0];
    render(<CustomFieldsPanel projectId={PROJECT} canEdit />);
    const section = await screen.findByTestId("project-custom-fields");
    await waitFor(() => {
      expect(within(section).getByText("Estimate")).toBeInTheDocument();
    });

    fireEvent.click(
      within(section).getByRole("button", { name: "projects.cfAdd" }),
    );
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(await findByLabel(dialog, "projects.cfKey"), {
      target: { value: "estimate" },
    });
    fireEvent.change(within(dialog).getByLabelText("projects.cfLabel"), {
      target: { value: "Estimate" },
    });

    // Pick the ``select`` type, then edit its option set.
    const typeSelect = within(dialog).getByLabelText("projects.cfType");
    fireEvent.mouseDown(typeSelect);
    fireEvent.click(
      within(
        document.querySelector(".ant-select-dropdown") as HTMLElement,
      ).getByText("projects.cfTypeSelect"),
    );
    const optionsInput = await findByLabel(dialog, "projects.cfOptions");
    for (const option of ["alpha", "beta"]) {
      fireEvent.mouseDown(optionsInput);
      fireEvent.change(optionsInput, { target: { value: option } });
      fireEvent.keyDown(optionsInput, { key: "Enter", keyCode: 13 });
    }

    fireEvent.click(
      within(dialog).getByRole("button", { name: "common.save" }),
    );

    await waitFor(() => {
      expect(callFor("POST", "/projects/p1/custom-fields")).toBeTruthy();
    });
    const [path, init] = callFor("POST", "/projects/p1/custom-fields");
    expect(path).toBe("/projects/p1/custom-fields");
    expect(init.method).toBe("POST");
    expect(bodyOf(init)).toEqual({
      key: "estimate",
      label: "Estimate",
      type: "select",
      required: false,
      options: ["alpha", "beta"],
      // Appends after the two existing definitions.
      sort_order: 2,
    });
  });

  it("edits label/required/options and keeps type and key read-only", async () => {
    routes["PATCH /projects/p1/custom-fields/f2"] = () => DEFINITIONS[1];
    render(<CustomFieldsPanel projectId={PROJECT} canEdit />);
    const section = await screen.findByTestId("project-custom-fields");
    await waitFor(() => {
      expect(within(section).getByText("Stage")).toBeInTheDocument();
    });

    const row = within(section).getByText("Stage").closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "common.edit" }));

    const dialog = await screen.findByRole("dialog");
    const keyInput = await findByLabel(dialog, "projects.cfKey");
    expect(keyInput).toBeDisabled();
    expect(within(dialog).getByLabelText("projects.cfType")).toBeDisabled();

    fireEvent.change(within(dialog).getByLabelText("projects.cfLabel"), {
      target: { value: "Stage v2" },
    });
    fireEvent.click(within(dialog).getByRole("switch"));
    const optionsInput = await findByLabel(dialog, "projects.cfOptions");
    fireEvent.mouseDown(optionsInput);
    fireEvent.change(optionsInput, { target: { value: "gamma" } });
    fireEvent.keyDown(optionsInput, { key: "Enter", keyCode: 13 });

    fireEvent.click(
      within(dialog).getByRole("button", { name: "common.save" }),
    );

    await waitFor(() => {
      expect(callFor("PATCH", "/projects/p1/custom-fields/f2")).toBeTruthy();
    });
    const body = bodyOf(callFor("PATCH", "/projects/p1/custom-fields/f2")[1]);
    expect(body).toEqual({
      label: "Stage v2",
      required: true,
      options: ["alpha", "beta", "gamma"],
      sort_order: 1,
    });
    expect(Object.keys(body)).not.toContain("key");
    expect(Object.keys(body)).not.toContain("type");
  });

  it("blocks a select definition without options", async () => {
    render(<CustomFieldsPanel projectId={PROJECT} canEdit />);
    const section = await screen.findByTestId("project-custom-fields");
    await waitFor(() => {
      expect(within(section).getByText("Estimate")).toBeInTheDocument();
    });

    fireEvent.click(
      within(section).getByRole("button", { name: "projects.cfAdd" }),
    );
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(await findByLabel(dialog, "projects.cfKey"), {
      target: { value: "stage" },
    });
    fireEvent.change(within(dialog).getByLabelText("projects.cfLabel"), {
      target: { value: "Stage" },
    });
    fireEvent.mouseDown(within(dialog).getByLabelText("projects.cfType"));
    fireEvent.click(
      within(
        document.querySelector(".ant-select-dropdown") as HTMLElement,
      ).getByText("projects.cfTypeSelect"),
    );
    await findByLabel(dialog, "projects.cfOptions");

    fireEvent.click(
      within(dialog).getByRole("button", { name: "common.save" }),
    );

    expect(
      await within(dialog).findByText("projects.cfInvalid"),
    ).toBeInTheDocument();
    expect(
      mockedRequest.mock.calls.some(
        ([path, init]) =>
          path === "/projects/p1/custom-fields" && init?.method === "POST",
      ),
    ).toBe(false);
  });

  it("asks for confirmation before deleting a definition", async () => {
    routes["DELETE /projects/p1/custom-fields/f1"] = () => ({ deleted: true });
    render(<CustomFieldsPanel projectId={PROJECT} canEdit />);
    const section = await screen.findByTestId("project-custom-fields");
    await waitFor(() => {
      expect(within(section).getByText("Estimate")).toBeInTheDocument();
    });

    const row = within(section)
      .getByText("Estimate")
      .closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "common.delete" }));

    expect(mockedConfirm).toHaveBeenCalledTimes(1);
    const confirmProps = mockedConfirm.mock.calls[0][0];
    expect(confirmProps.title).toBe("projects.cfDeleteConfirm");
    expect(confirmProps.okType).toBe("danger");

    await act(async () => {
      await confirmProps.onOk?.();
    });
    expect(callFor("DELETE", "/projects/p1/custom-fields/f1")).toBeTruthy();
  });

  it("does not leak the edited definition into a new one", async () => {
    render(<CustomFieldsPanel projectId={PROJECT} canEdit />);
    const section = await screen.findByTestId("project-custom-fields");
    await waitFor(() => {
      expect(within(section).getByText("Stage")).toBeInTheDocument();
    });

    const row = within(section).getByText("Stage").closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "common.edit" }));
    let dialog = await screen.findByRole("dialog");
    expect(await findByLabel(dialog, "projects.cfKey")).toHaveValue("stage");

    fireEvent.click(
      within(dialog).getByRole("button", { name: "common.cancel" }),
    );
    await waitFor(() => {
      expect(screen.queryByLabelText("projects.cfKey")).toBeNull();
    });

    fireEvent.click(
      within(section).getByRole("button", { name: "projects.cfAdd" }),
    );
    dialog = await screen.findByRole("dialog");
    expect(await findByLabel(dialog, "projects.cfKey")).toHaveValue("");
    expect(within(dialog).getByLabelText("projects.cfLabel")).toHaveValue("");
    expect(within(dialog).getByRole("switch")).not.toBeChecked();
  });

  it("hides the write affordances for a read-only viewer", async () => {
    render(<CustomFieldsPanel projectId={PROJECT} canEdit={false} />);
    const section = await screen.findByTestId("project-custom-fields");
    await waitFor(() => {
      expect(within(section).getByText("Estimate")).toBeInTheDocument();
    });

    expect(
      within(section).queryByRole("button", { name: "projects.cfAdd" }),
    ).not.toBeInTheDocument();
    expect(
      within(section).queryByRole("button", { name: "common.delete" }),
    ).not.toBeInTheDocument();
  });
});

describe("TagsManager", () => {
  it("lists tag definitions with name, color and a server-timezone date", async () => {
    render(<TagsManager projectId={PROJECT} canEdit />);
    const section = await screen.findByTestId("project-tags");

    await waitFor(() => {
      expect(within(section).getByText("urgent")).toBeInTheDocument();
    });
    expect(within(section).getByText("#ff0000")).toBeInTheDocument();
    expect(within(section).getByText("later")).toBeInTheDocument();
    expect(
      within(section).getByText(formatServerDateTime(1700000300, "UTC")),
    ).toBeInTheDocument();
  });

  it("renders an empty state instead of an empty control", async () => {
    routes["GET /projects/p1/tags"] = () => [];
    render(<TagsManager projectId={PROJECT} canEdit />);

    const empty = await screen.findByTestId("tags-empty");
    expect(within(empty).getByText("projects.tagsEmpty")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("creates a tag with name and color", async () => {
    routes["POST /projects/p1/tags"] = () => TAGS[0];
    render(<TagsManager projectId={PROJECT} canEdit />);
    const section = await screen.findByTestId("project-tags");
    await waitFor(() => {
      expect(within(section).getByText("urgent")).toBeInTheDocument();
    });

    fireEvent.click(
      within(section).getByRole("button", { name: "projects.tagCreate" }),
    );
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(await findByLabel(dialog, "projects.tagName"), {
      target: { value: "blocked" },
    });
    fireEvent.change(within(dialog).getByLabelText("projects.tagColor"), {
      target: { value: "#00FF00" },
    });

    fireEvent.click(
      within(dialog).getByRole("button", { name: "common.save" }),
    );

    await waitFor(() => {
      expect(callFor("POST", "/projects/p1/tags")).toBeTruthy();
    });
    const [path, init] = callFor("POST", "/projects/p1/tags");
    expect(path).toBe("/projects/p1/tags");
    expect(bodyOf(init)).toEqual({ name: "blocked", color: "#00ff00" });
  });

  it("rejects an invalid color before submitting", async () => {
    render(<TagsManager projectId={PROJECT} canEdit />);
    const section = await screen.findByTestId("project-tags");
    await waitFor(() => {
      expect(within(section).getByText("urgent")).toBeInTheDocument();
    });

    fireEvent.click(
      within(section).getByRole("button", { name: "projects.tagCreate" }),
    );
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(await findByLabel(dialog, "projects.tagName"), {
      target: { value: "blocked" },
    });
    fireEvent.change(within(dialog).getByLabelText("projects.tagColor"), {
      target: { value: "red" },
    });

    fireEvent.click(
      within(dialog).getByRole("button", { name: "common.save" }),
    );

    expect(
      await within(dialog).findByText("projects.tagInvalid"),
    ).toBeInTheDocument();
    expect(
      mockedRequest.mock.calls.some(
        ([path, init]) =>
          path === "/projects/p1/tags" && init?.method === "POST",
      ),
    ).toBe(false);
  });

  it("renames and recolors a tag through the update body", async () => {
    routes["PATCH /projects/p1/tags/t2"] = () => TAGS[1];
    render(<TagsManager projectId={PROJECT} canEdit />);
    const section = await screen.findByTestId("project-tags");
    await waitFor(() => {
      expect(within(section).getByText("later")).toBeInTheDocument();
    });

    const row = within(section).getByText("later").closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "common.edit" }));

    const dialog = await screen.findByRole("dialog");
    fireEvent.change(await findByLabel(dialog, "projects.tagName"), {
      target: { value: "later v2" },
    });
    fireEvent.change(within(dialog).getByLabelText("projects.tagColor"), {
      target: { value: "#0000ff" },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "common.save" }),
    );

    await waitFor(() => {
      expect(callFor("PATCH", "/projects/p1/tags/t2")).toBeTruthy();
    });
    expect(bodyOf(callFor("PATCH", "/projects/p1/tags/t2")[1])).toEqual({
      name: "later v2",
      color: "#0000ff",
    });
  });

  it("warns that deleting a tag removes it from tasks", async () => {
    routes["DELETE /projects/p1/tags/t1"] = () => ({ deleted: true });
    render(<TagsManager projectId={PROJECT} canEdit />);
    const section = await screen.findByTestId("project-tags");
    await waitFor(() => {
      expect(within(section).getByText("urgent")).toBeInTheDocument();
    });

    const row = within(section)
      .getByText("urgent")
      .closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "common.delete" }));

    expect(mockedConfirm).toHaveBeenCalledTimes(1);
    const confirmProps = mockedConfirm.mock.calls[0][0];
    expect(confirmProps.title).toBe("projects.tagDeleteConfirm");

    await act(async () => {
      await confirmProps.onOk?.();
    });
    expect(callFor("DELETE", "/projects/p1/tags/t1")).toBeTruthy();
  });

  it("does not leak the edited tag into a new one", async () => {
    render(<TagsManager projectId={PROJECT} canEdit />);
    const section = await screen.findByTestId("project-tags");
    await waitFor(() => {
      expect(within(section).getByText("later")).toBeInTheDocument();
    });

    const row = within(section).getByText("later").closest("tr") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "common.edit" }));
    let dialog = await screen.findByRole("dialog");
    expect(await findByLabel(dialog, "projects.tagName")).toHaveValue("later");

    fireEvent.click(
      within(dialog).getByRole("button", { name: "common.cancel" }),
    );
    await waitFor(() => {
      expect(screen.queryByLabelText("projects.tagName")).toBeNull();
    });

    fireEvent.click(
      within(section).getByRole("button", { name: "projects.tagCreate" }),
    );
    dialog = await screen.findByRole("dialog");
    expect(await findByLabel(dialog, "projects.tagName")).toHaveValue("");
    expect(within(dialog).getByLabelText("projects.tagColor")).toHaveValue("");
  });

  it("hides the write affordances for a read-only viewer", async () => {
    render(<TagsManager projectId={PROJECT} canEdit={false} />);
    const section = await screen.findByTestId("project-tags");
    await waitFor(() => {
      expect(within(section).getByText("urgent")).toBeInTheDocument();
    });

    expect(
      within(section).queryByRole("button", { name: "projects.tagCreate" }),
    ).not.toBeInTheDocument();
  });
});
