import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Checkbox } from "antd";
import type { KnowledgeDocument } from "../../api/modules/knowledgeBases";
import { knowledgeBasesApi } from "../../api/modules/knowledgeBases";
import DocumentBatchActions from "./DocumentBatchActions";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { completed?: number; total?: number }) =>
      key === "knowledgeBases.batchProgress"
        ? `${options?.completed}/${options?.total}`
        : key,
  }),
}));

vi.mock("../../api/modules/knowledgeBases", () => ({
  knowledgeBasesApi: { deleteDocument: vi.fn(), reindexDocument: vi.fn() },
}));
const doc = (id: string, is_dir = false) =>
  ({ id, filename: `${id}.md`, is_dir }) as KnowledgeDocument;
function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function mount(
  documents = [doc("one"), doc("two"), doc("dir", true)],
  writable = true,
) {
  const onChanged = vi.fn().mockResolvedValue(undefined);
  const view = render(
    <DocumentBatchActions
      kbId="kb-one"
      documents={documents}
      writable={writable}
      onChanged={onChanged}
    >
      {(selection) => (
        <>
          {documents
            .filter((d) => !d.is_dir)
            .map((d) => (
              <Checkbox
                key={d.id}
                checked={selection.keys.includes(d.id)}
                disabled={selection.busy || !writable}
                onChange={(e) =>
                  selection.setKeys(
                    e.target.checked
                      ? [...selection.keys, d.id]
                      : selection.keys.filter((id) => id !== d.id),
                  )
                }
              >
                {d.filename}
              </Checkbox>
            ))}
        </>
      )}
    </DocumentBatchActions>,
  );
  return { ...view, onChanged };
}
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(knowledgeBasesApi.deleteDocument).mockResolvedValue({ ok: true });
  vi.mocked(knowledgeBasesApi.reindexDocument).mockResolvedValue(
    doc("reindexed"),
  );
});

describe("knowledge document batch operations", () => {
  it("keeps progress tied to the snapshot while polling changes the list", async () => {
    const user = userEvent.setup();
    const hold = deferred();
    vi.mocked(knowledgeBasesApi.reindexDocument).mockImplementation(
      async (_kb, id) => {
        await hold.promise;
        return doc(id);
      },
    );
    const { rerender, onChanged } = mount([doc("one"), doc("two")]);
    await user.click(
      screen.getByRole("checkbox", { name: "knowledgeBases.batchSelectAll" }),
    );
    await user.click(
      screen.getByRole("button", { name: "knowledgeBases.batchReindex" }),
    );
    rerender(
      <DocumentBatchActions
        kbId="kb-one"
        documents={[doc("two")]}
        writable
        onChanged={onChanged}
      >
        {() => null}
      </DocumentBatchActions>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("0/2");
    await act(async () => hold.resolve());
  });
  it("stops dispatch and refresh immediately when navigation intent changes", async () => {
    const user = userEvent.setup();
    const hold = deferred();
    let current = true;
    const onChanged = vi.fn();
    vi.mocked(knowledgeBasesApi.reindexDocument).mockImplementation(
      async (_kb, id) => {
        await hold.promise;
        return doc(id);
      },
    );
    render(
      <DocumentBatchActions
        kbId="kb-one"
        documents={Array.from({ length: 8 }, (_, i) => doc(String(i)))}
        writable
        onChanged={onChanged}
        isCurrent={() => current}
      >
        {() => null}
      </DocumentBatchActions>,
    );
    await user.click(
      screen.getByRole("checkbox", { name: "knowledgeBases.batchSelectAll" }),
    );
    await user.click(
      screen.getByRole("button", { name: "knowledgeBases.batchReindex" }),
    );
    current = false;
    await act(async () => hold.resolve());
    expect(knowledgeBasesApi.reindexDocument).toHaveBeenCalledTimes(3);
    expect(onChanged).not.toHaveBeenCalled();
  });
  it("drains a bounded queue and refreshes once after all requests settle", async () => {
    const user = userEvent.setup();
    const holds = Array.from({ length: 8 }, deferred);
    vi.mocked(knowledgeBasesApi.reindexDocument).mockImplementation(
      async (_kb, id) => {
        await holds[Number(id)].promise;
        return doc(id);
      },
    );
    const { onChanged } = mount(
      Array.from({ length: 8 }, (_, i) => doc(String(i))),
    );
    await user.click(
      screen.getByRole("checkbox", { name: "knowledgeBases.batchSelectAll" }),
    );
    await user.click(
      screen.getByRole("button", { name: "knowledgeBases.batchReindex" }),
    );
    expect(knowledgeBasesApi.reindexDocument).toHaveBeenCalledTimes(3);
    await act(async () => holds[1].resolve());
    expect(knowledgeBasesApi.reindexDocument).toHaveBeenCalledTimes(4);
    expect(onChanged).not.toHaveBeenCalled();
    await act(async () => {
      for (const hold of holds) hold.resolve();
    });
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(
      knowledgeBasesApi.reindexDocument.mock.calls.map(([_kb, id]) => id),
    ).toEqual(["0", "1", "2", "3", "4", "5", "6", "7"]);
  });
  it("selects only files and requires confirmation before deleting", async () => {
    const user = userEvent.setup();
    const { onChanged } = mount();
    await user.click(
      screen.getByRole("checkbox", { name: "knowledgeBases.batchSelectAll" }),
    );
    await user.click(
      screen.getByRole("button", { name: "knowledgeBases.batchDelete" }),
    );
    expect(knowledgeBasesApi.deleteDocument).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "common.confirm" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(knowledgeBasesApi.deleteDocument.mock.calls).toEqual([
      ["kb-one", "one"],
      ["kb-one", "two"],
    ]);
    expect(screen.getByRole("checkbox", { name: "one.md" })).not.toBeChecked();
  });
  it("retains only failures for retry and reports each error", async () => {
    const user = userEvent.setup();
    vi.mocked(knowledgeBasesApi.reindexDocument).mockImplementation(
      async (_kb, id) => {
        if (id === "two") throw new Error("denied");
        return doc(id);
      },
    );
    const { onChanged } = mount();
    await user.click(
      screen.getByRole("checkbox", { name: "knowledgeBases.batchSelectAll" }),
    );
    await user.click(
      screen.getByRole("button", { name: "knowledgeBases.batchReindex" }),
    );
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("checkbox", { name: "one.md" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "two.md" })).toBeChecked();
    expect(screen.getByText("denied")).toBeInTheDocument();
    vi.mocked(knowledgeBasesApi.reindexDocument).mockResolvedValue(doc("two"));
    await user.click(
      screen.getByRole("button", { name: "knowledgeBases.batchReindex" }),
    );
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(2));
    expect(knowledgeBasesApi.reindexDocument).toHaveBeenCalledTimes(3);
  });
  it("bounds requests, blocks repeated actions, and stops dispatch after unmount", async () => {
    const user = userEvent.setup();
    const hold = deferred();
    vi.mocked(knowledgeBasesApi.reindexDocument).mockImplementation(
      async (_kb, id) => {
        await hold.promise;
        return doc(id);
      },
    );
    const { unmount, onChanged } = mount(
      Array.from({ length: 8 }, (_, i) => doc(String(i))),
    );
    await user.click(
      screen.getByRole("checkbox", { name: "knowledgeBases.batchSelectAll" }),
    );
    await user.click(
      screen.getByRole("button", { name: "knowledgeBases.batchReindex" }),
    );
    await waitFor(() =>
      expect(knowledgeBasesApi.reindexDocument).toHaveBeenCalledTimes(3),
    );
    expect(
      screen.getByRole("button", { name: "knowledgeBases.batchDelete" }),
    ).toBeDisabled();
    unmount();
    await act(async () => hold.resolve());
    expect(knowledgeBasesApi.reindexDocument).toHaveBeenCalledTimes(3);
    expect(onChanged).not.toHaveBeenCalled();
  });
  it("keeps read-only users out of bulk operations", () => {
    mount(undefined, false);
    expect(
      screen.queryByRole("button", { name: "knowledgeBases.batchDelete" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("checkbox", { name: "knowledgeBases.batchSelectAll" }),
    ).not.toBeInTheDocument();
  });
  it("does not retry a successful mutation when refreshing fails", async () => {
    const user = userEvent.setup();
    const { onChanged } = mount([doc("one")]);
    onChanged.mockRejectedValue(new Error("refresh offline"));
    await user.click(screen.getByRole("checkbox", { name: "one.md" }));
    await user.click(
      screen.getByRole("button", { name: "knowledgeBases.batchReindex" }),
    );
    await screen.findByText("knowledgeBases.batchRefreshFailed");
    expect(screen.getByRole("checkbox", { name: "one.md" })).not.toBeChecked();
    expect(knowledgeBasesApi.reindexDocument).toHaveBeenCalledTimes(1);
  });
});
