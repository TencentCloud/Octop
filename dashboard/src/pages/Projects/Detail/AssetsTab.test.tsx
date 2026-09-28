import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Only the transport is mocked: the tab must go through the shared
// ``knowledgeBasesApi`` wrapper, so asserting on ``request`` proves the real
// path and proves that the empty branch issues nothing at all.
vi.mock("../../../api/request", () => ({
  request: vi.fn(),
  requestBlob: vi.fn(),
  requestUpload: vi.fn(),
}));

// ``useServerTimezone`` fetches the server timezone on its own; pinning it keeps
// the request count attributable to the knowledge-base read alone.
vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "UTC",
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
import AssetsTab from "./AssetsTab";
import DynamicTab from "./DynamicTab";

const mockedRequest = vi.mocked(request);

const KB = {
  id: "kb1",
  owner_user_id: 1,
  name: "Project Alpha KB",
  description: "",
  default_open: false,
  shared: false,
  icon_name: "",
  embedding_model: "m",
  embedding_dim: 768,
  doc_count: 7,
  max_documents: 100,
  created_at: 1700000000,
  updated_at: 1700000100,
};

function renderTab(node: React.ReactElement) {
  return render(
    <MemoryRouter initialEntries={["/projects/p1"]}>{node}</MemoryRouter>,
  );
}

beforeEach(() => {
  mockedRequest.mockReset();
});

describe("assets tab — data source is projects.kb_id (PLAN §19.3)", () => {
  it("renders the empty branch and issues no request when kb_id is null", async () => {
    renderTab(<AssetsTab kbId={null} />);

    // ★ Assert the branch that was taken, not merely that nothing threw: the
    //   empty-state marker can only exist on the no-kb path.
    expect(
      await screen.findByTestId("project-assets-empty"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("project-assets")).not.toBeInTheDocument();
    expect(screen.getByText("projects.assetEmpty")).toBeInTheDocument();
    expect(screen.getByText("projects.assetBind")).toBeInTheDocument();

    // A null kb_id is a supported state, so it must not read anything.
    await waitFor(() => expect(mockedRequest).not.toHaveBeenCalled());
  });

  it("loads the bound knowledge base and shows its name, count and updated time", async () => {
    mockedRequest.mockResolvedValue(KB as never);
    renderTab(<AssetsTab kbId="kb1" />);

    expect(await screen.findByTestId("project-assets")).toBeInTheDocument();
    expect(
      screen.queryByTestId("project-assets-empty"),
    ).not.toBeInTheDocument();

    await waitFor(() => expect(mockedRequest).toHaveBeenCalledTimes(1));
    expect(mockedRequest.mock.calls[0][0]).toBe("/knowledge-bases/kb1");

    expect(await screen.findByText("Project Alpha KB")).toBeInTheDocument();
    // The count is rendered through the frozen key with its placeholder filled.
    expect(screen.getByText("projects.assetDocCount")).toBeInTheDocument();
    expect(screen.getByText("projects.assetOpen")).toBeInTheDocument();
  });

  it("re-reads the knowledge base when kb_id changes", async () => {
    mockedRequest.mockResolvedValue(KB as never);
    const { rerender } = renderTab(<AssetsTab kbId="kb1" />);
    await waitFor(() => expect(mockedRequest).toHaveBeenCalledTimes(1));

    rerender(
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <AssetsTab kbId="kb2" />
      </MemoryRouter>,
    );
    await waitFor(() => expect(mockedRequest).toHaveBeenCalledTimes(2));
    expect(mockedRequest.mock.calls[1][0]).toBe("/knowledge-bases/kb2");
  });
});

describe("activity tab — a placeholder, not the feed (PLAN §4.1)", () => {
  it("renders the placeholder copy and never touches the network", async () => {
    renderTab(<DynamicTab />);

    expect(await screen.findByTestId("project-dynamic")).toBeInTheDocument();
    expect(screen.getByText("projects.dynamicPlaceholder")).toBeInTheDocument();
    expect(screen.getByText("projects.dynamicComingSoon")).toBeInTheDocument();

    // ★ The hard part of "this is only a placeholder": it must not fetch a feed.
    //   The feed belongs to the next batch, so any call here would be scope
    //   leaking into this one.
    await waitFor(() => expect(mockedRequest).not.toHaveBeenCalled());
  });
});
