import {
  StrictMode,
  useState,
  type ComponentType,
  type ReactNode,
} from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  makeAtom,
  makeCandidate,
  makeEntity,
  makeEpisode,
  makeJournal,
} from "../../../test/memoryFixtures";

const mocks = vi.hoisted(() => ({
  atoms: vi.fn(),
  raw: vi.fn(),
  episodes: vi.fn(),
  journal: vi.fn(),
  candidates: vi.fn(),
  entities: vi.fn(),
  threads: vi.fn(),
  history: vi.fn(),
  removeThread: vi.fn(),
  promote: vi.fn(),
  reject: vi.fn(),
  edit: vi.fn(),
  deprecate: vi.fn(),
  destroyAction: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
  createProps: null as null | {
    onSuccess: () => void;
    onClose: () => void;
    entities: { canonical_name: string }[];
    open: boolean;
  },
  t: (key: string, fallback?: unknown) =>
    typeof fallback === "string" ? fallback : key,
}));

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: mocks.t }) }));
vi.mock("../../../hooks/useIsMobile", () => ({ useIsMobile: () => false }));
vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "UTC",
}));
vi.mock("../../../utils/antdMessage", () => ({
  message: { error: mocks.error, success: mocks.success },
}));
vi.mock("../../../api/modules/memoryDashboard", () => ({
  memoryDashboardApi: {
    listAtoms: mocks.atoms,
    listRawEvents: mocks.raw,
    listEpisodes: mocks.episodes,
    listJournal: mocks.journal,
    listCandidates: mocks.candidates,
    listEntities: mocks.entities,
    promoteCandidate: mocks.promote,
    rejectCandidate: mocks.reject,
  },
  isAtomDeprecated: () => false,
}));
vi.mock("../../../api/modules/octopThreads", () => ({
  CHAT_HISTORY_PAGE_SIZE: 50,
  octopThreadsApi: {
    list: mocks.threads,
    history: mocks.history,
    delete: mocks.removeThread,
  },
}));
vi.mock("./shared/LineageStrip", () => ({ default: () => null }));
vi.mock("./shared/MemoryPipelineEmpty", () => ({ default: () => null }));
vi.mock("../../../components/Markdown/LazyMarkdown", () => ({
  default: () => null,
}));
vi.mock("./shared/editAtom", () => ({ confirmEditAtom: mocks.edit }));
vi.mock("./shared/deprecateAtom", () => ({
  confirmDeprecateAtom: mocks.deprecate,
}));
vi.mock("./shared/createAtom", () => ({
  default: (props: NonNullable<typeof mocks.createProps>) => {
    mocks.createProps = props;
    return (
      <output data-testid="entities">
        {props.entities.map((entity) => entity.canonical_name).join(",")}
      </output>
    );
  },
}));

// Keep the real list components and their event handlers. Lightweight display
// controls expose loading/count state without Antd animation or portal timing.
vi.mock("antd", async (importOriginal) => {
  const actual = await importOriginal<typeof import("antd")>();
  const Pagination = ({
    total,
    current = 1,
    onChange,
  }: {
    total: number;
    current?: number;
    onChange?: (page: number) => void;
  }) => (
    <div>
      <output data-testid="total">{total}</output>
      <output data-testid="page">{current}</output>
      {[2, 3].map((page) => (
        <button key={page} onClick={() => onChange?.(page)}>
          page {page}
        </button>
      ))}
    </div>
  );
  return {
    ...actual,
    Skeleton: () => <div data-testid="loading" />,
    Pagination,
    Select: ({
      value,
      onChange,
      options,
    }: {
      value: string;
      onChange: (value: string) => void;
      options: { value: string; label: string }[];
    }) => (
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    ),
    Drawer: ({ open, children }: { open: boolean; children: ReactNode }) =>
      open ? <section role="dialog">{children}</section> : null,
    Modal: ({
      open,
      children,
      onOk,
      confirmLoading,
    }: {
      open: boolean;
      children: ReactNode;
      onOk: () => void;
      confirmLoading: boolean;
    }) =>
      open ? (
        <section
          role="dialog"
          data-testid="reject-modal"
          data-loading={confirmLoading}
        >
          {children}
          <button onClick={onOk}>confirm reject</button>
        </section>
      ) : null,
    Popconfirm: ({
      children,
      onConfirm,
      disabled,
    }: {
      children: ReactNode;
      onConfirm: () => void;
      disabled?: boolean;
    }) => (
      <span>
        {children}
        <button disabled={disabled} onClick={onConfirm}>
          confirm action
        </button>
      </span>
    ),
    Table: function Table({
      dataSource,
      loading,
      columns,
      pagination,
    }: {
      dataSource: { thread_id: string; title: string }[];
      loading: boolean;
      columns: {
        key?: string;
        render?: (
          value: undefined,
          row: { thread_id: string; title: string },
        ) => ReactNode;
      }[];
      pagination: {
        current?: number;
        onChange?: (page: number, size: number) => void;
        pageSize?: number;
      };
    }) {
      const [page, setPage] = useState(1);
      return (
        <div>
          {loading && <div data-testid="loading" />}
          <Pagination
            total={dataSource.length}
            current={pagination.current ?? page}
            onChange={(page) => {
              setPage(page);
              pagination.onChange?.(page, pagination.pageSize ?? 20);
            }}
          />
          {dataSource.map((row) => (
            <div key={row.thread_id}>
              <span>{row.title}</span>
              {columns
                .find((column) => column.key === "actions")
                ?.render?.(undefined, row)}
            </div>
          ))}
        </div>
      );
    },
  };
});

import AtomsList from "./AtomsList";
import RawEventsList from "./RawEventsList";
import EpisodesList from "./EpisodesList";
import JournalList from "./JournalList";
import CandidatesReview from "./CandidatesReview";
import ConversationRecords from "./ConversationRecords";

function deferred() {
  let resolve!: (value: unknown) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const cases = [
  {
    name: "atoms",
    View: AtomsList,
    api: mocks.atoms,
    pageSize: 20,
    item: (label: string) => makeAtom({ id: label, assertion: label }),
    filters: ["Fact", "Task"],
  },
  {
    name: "raw",
    View: RawEventsList,
    api: mocks.raw,
    pageSize: 20,
    item: (label: string) => ({
      id: label,
      content: label,
      event_type: "user_message",
      timestamp: "2026-09-01T00:00:00Z",
    }),
    filters: ["user_message", "assistant_message"],
  },
  {
    name: "episodes",
    View: EpisodesList,
    api: mocks.episodes,
    pageSize: 20,
    item: (label: string) => makeEpisode({ id: label, summary: label }),
  },
  {
    name: "journal",
    View: JournalList,
    api: mocks.journal,
    pageSize: 30,
    item: (label: string) => makeJournal({ id: label, target_summary: label }),
    filters: ["promote", "reject"],
  },
  {
    name: "candidates",
    View: CandidatesReview,
    api: mocks.candidates,
    pageSize: 20,
    item: (label: string) => makeCandidate({ id: label, title: label }),
    filters: ["pending", "promoted"],
  },
  {
    name: "threads",
    View: ConversationRecords,
    api: mocks.threads,
    item: (label: string) => ({
      thread_id: label,
      title: label,
      channel_type: "web",
      created_at: 1,
      last_active: 2,
    }),
  },
];

function response(testCase: (typeof cases)[number], label: string, total = 1) {
  const items = [testCase.item(label)];
  return testCase.name === "threads"
    ? Array.from({ length: total }, (_, index) =>
        testCase.item(index ? `${label}-${index}` : label),
      )
    : { items, total, has_more: total > 1 };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.promote.mockReset();
  mocks.reject.mockReset();
  mocks.removeThread.mockReset();
  for (const testCase of cases) testCase.api.mockReset();
  mocks.entities
    .mockReset()
    .mockResolvedValue({ items: [], total: 0, has_more: false });
  mocks.history.mockResolvedValue({ messages: [], has_more: false });
  mocks.createProps = null;
  mocks.edit.mockReturnValue({ destroy: mocks.destroyAction });
  mocks.deprecate.mockReturnValue({ destroy: mocks.destroyAction });
});

describe.each(cases)("$name list request ownership", (testCase) => {
  const View: ComponentType<{ agentId: string }> = testCase.View;

  it("keeps B's rows and count when A completes last", async () => {
    const old = deferred();
    const current = deferred();
    testCase.api
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(current.promise);
    const { rerender } = render(<View agentId="A" />);
    rerender(<View agentId="B" />);
    await act(async () =>
      current.resolve(response(testCase, "current-row", 2)),
    );
    await act(async () => old.resolve(response(testCase, "obsolete-row", 3)));
    expect(screen.getByText(/^「?current-row」?$/)).toBeInTheDocument();
    expect(screen.queryByText(/obsolete-row/)).not.toBeInTheDocument();
    expect(screen.getByTestId("total")).toHaveTextContent(/^2$/);
  });

  it.each(["resolve", "reject"] as const)(
    "ignores obsolete %s while B is pending",
    async (outcome) => {
      const old = deferred();
      const current = deferred();
      testCase.api
        .mockReturnValueOnce(old.promise)
        .mockReturnValueOnce(current.promise);
      const { rerender } = render(<View agentId="A" />);
      rerender(<View agentId="B" />);
      await act(async () => {
        if (outcome === "resolve")
          old.resolve(response(testCase, "obsolete-row"));
        else old.reject(new Error("obsolete failure"));
      });
      expect(screen.getByTestId("loading")).toBeInTheDocument();
      expect(screen.queryByText(/obsolete-row/)).not.toBeInTheDocument();
      expect(mocks.error).not.toHaveBeenCalled();
      await act(async () => current.resolve(response(testCase, "current-row")));
      expect(screen.queryByTestId("loading")).not.toBeInTheDocument();
    },
  );

  it("does not clear B's successful result when A fails later", async () => {
    const old = deferred();
    testCase.api
      .mockReturnValueOnce(old.promise)
      .mockResolvedValueOnce(response(testCase, "current-row"));
    const { rerender } = render(<View agentId="A" />);
    await act(async () => rerender(<View agentId="B" />));
    await act(async () => old.reject(new Error("obsolete failure")));
    expect(screen.getByText(/^「?current-row」?$/)).toBeInTheDocument();
    expect(mocks.error).not.toHaveBeenCalled();
  });

  it("clears previously loaded rows and count before B responds", async () => {
    testCase.api.mockResolvedValueOnce(response(testCase, "obsolete-row", 2));
    const { rerender } = render(<View agentId="A" />);
    await act(async () => {});
    expect(screen.getByText(/^「?obsolete-row」?$/)).toBeInTheDocument();
    testCase.api.mockReturnValue(new Promise(() => {}));
    rerender(<View agentId="B" />);
    expect(screen.queryByText(/obsolete-row/)).not.toBeInTheDocument();
    expect(screen.getByTestId("total")).toHaveTextContent(/^0$/);
    expect(screen.getByTestId("loading")).toBeInTheDocument();
    await act(async () => {});
  });

  it("distinguishes two visits to A separated by B", async () => {
    const old = deferred();
    testCase.api
      .mockReturnValueOnce(old.promise)
      .mockResolvedValue(response(testCase, "current-row"));
    const { rerender } = render(<View agentId="A" />);
    await act(async () => rerender(<View agentId="B" />));
    await act(async () => rerender(<View agentId="A" />));
    await act(async () => old.resolve(response(testCase, "obsolete-row")));
    expect(screen.getByText(/^「?current-row」?$/)).toBeInTheDocument();
    expect(screen.queryByText(/obsolete-row/)).not.toBeInTheDocument();
  });

  it("ignores a failure after unmount", async () => {
    const pending = deferred();
    testCase.api.mockReturnValue(pending.promise);
    const { unmount } = render(<View agentId="A" />);
    unmount();
    await act(async () => pending.reject(new Error("unmounted failure")));
    expect(mocks.error).not.toHaveBeenCalled();
  });

  it("survives StrictMode effect cleanup and replay", async () => {
    const old = deferred();
    testCase.api
      .mockReturnValueOnce(old.promise)
      .mockResolvedValue(response(testCase, "current-row"));
    render(
      <StrictMode>
        <View agentId="A" />
      </StrictMode>,
    );
    await act(async () => {});
    await act(async () => old.resolve(response(testCase, "obsolete-row")));
    expect(screen.getByText(/^「?current-row」?$/)).toBeInTheDocument();
    expect(screen.queryByText(/obsolete-row/)).not.toBeInTheDocument();
  });
});

describe.each(cases.filter((testCase) => testCase.pageSize))(
  "$name pagination",
  (testCase) => {
    it("keeps the latest page when responses arrive out of order, and resets the page for a new agent", async () => {
      const View = testCase.View;
      testCase.api.mockResolvedValueOnce(
        response(testCase, "initial-row", 200),
      );
      const { rerender } = render(<View agentId="A" />);
      await act(async () => {});
      const old = deferred();
      const current = deferred();
      testCase.api
        .mockReturnValueOnce(old.promise)
        .mockReturnValueOnce(current.promise);
      fireEvent.click(screen.getByText("page 2"));
      fireEvent.click(screen.getByText("page 3"));
      await act(async () =>
        current.resolve(response(testCase, "current-row", 200)),
      );
      await act(async () =>
        old.resolve(response(testCase, "obsolete-row", 100)),
      );
      expect(screen.getByText(/^「?current-row」?$/)).toBeInTheDocument();
      expect(screen.getByTestId("page")).toHaveTextContent(/^3$/);
      expect(screen.getByTestId("total")).toHaveTextContent(/^200$/);
      testCase.api.mockResolvedValue(response(testCase, "new-agent-row"));
      await act(async () => rerender(<View agentId="B" />));
      expect(screen.getByTestId("page")).toHaveTextContent(/^1$/);
      expect(testCase.api).toHaveBeenLastCalledWith(
        "B",
        expect.objectContaining({ offset: 0 }),
      );
    });
  },
);

describe.each(cases.filter((testCase) => testCase.filters))(
  "$name filters",
  (testCase) => {
    it("keeps the latest filter result and preserves the filter on agent change", async () => {
      const View = testCase.View;
      testCase.api.mockResolvedValueOnce(response(testCase, "initial-row"));
      const { rerender } = render(<View agentId="A" />);
      await act(async () => {});
      const old = deferred();
      const current = deferred();
      testCase.api
        .mockReturnValueOnce(old.promise)
        .mockReturnValueOnce(current.promise);
      const select = screen.getAllByRole("combobox")[0];
      fireEvent.change(select, { target: { value: testCase.filters![0] } });
      fireEvent.change(select, { target: { value: testCase.filters![1] } });
      await act(async () => current.resolve(response(testCase, "current-row")));
      await act(async () => old.resolve(response(testCase, "obsolete-row")));
      expect(screen.getByText(/^「?current-row」?$/)).toBeInTheDocument();
      expect(screen.queryByText(/obsolete-row/)).not.toBeInTheDocument();
      testCase.api.mockResolvedValue(response(testCase, "new-agent-row"));
      await act(async () => rerender(<View agentId="B" />));
      expect(screen.getAllByRole("combobox")[0]).toHaveValue(
        testCase.filters![1],
      );
    });
  },
);

describe.each(
  cases.filter((testCase) =>
    ["raw", "episodes", "candidates"].includes(testCase.name),
  ),
)("$name selection", (testCase) => {
  it("closes the old detail on agent change", async () => {
    const View = testCase.View;
    testCase.api.mockResolvedValue(response(testCase, "visible-row"));
    const { rerender } = render(<View agentId="A" />);
    await act(async () => {});
    fireEvent.click(screen.getByText("visible-row"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    testCase.api.mockReturnValue(new Promise(() => {}));
    rerender(<View agentId="B" />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe.each(
  cases.filter((testCase) => ["candidates", "threads"].includes(testCase.name)),
)("$name current errors", (testCase) => {
  it("still reports the current failure and does not accept an older success", async () => {
    const View = testCase.View;
    const old = deferred();
    testCase.api
      .mockReturnValueOnce(old.promise)
      .mockRejectedValueOnce(new Error("current failure"));
    const { rerender } = render(<View agentId="A" />);
    await act(async () => rerender(<View agentId="B" />));
    expect(mocks.error).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("loading")).not.toBeInTheDocument();
    await act(async () => old.resolve(response(testCase, "obsolete-row")));
    expect(screen.queryByText(/obsolete-row/)).not.toBeInTheDocument();
    expect(screen.getByTestId("total")).toHaveTextContent(/^0$/);
  });
});

describe("Atoms related requests and callbacks", () => {
  it.each(["resolve", "reject"] as const)(
    "ignores obsolete entity %s without invalidating the atom request",
    async (outcome) => {
      const old = deferred();
      const currentAtoms = deferred();
      mocks.atoms
        .mockReturnValueOnce(new Promise(() => {}))
        .mockReturnValueOnce(currentAtoms.promise);
      mocks.entities.mockReturnValueOnce(old.promise).mockResolvedValueOnce({
        items: [makeEntity({ canonical_name: "B entity" })],
      });
      const { rerender } = render(<AtomsList agentId="A" />);
      await act(async () => rerender(<AtomsList agentId="B" />));
      await act(async () => {
        if (outcome === "resolve")
          old.resolve({ items: [makeEntity({ canonical_name: "A entity" })] });
        else old.reject(new Error("old entities"));
        currentAtoms.resolve({
          items: [makeAtom({ assertion: "B atom" })],
          total: 1,
        });
      });
      expect(screen.getByTestId("entities")).toHaveTextContent(/^B entity$/);
      expect(screen.getByText("B atom")).toBeInTheDocument();
    },
  );

  it("gates repeated creation refreshes for both atoms and entities", async () => {
    mocks.atoms.mockResolvedValue({ items: [], total: 0 });
    render(<AtomsList agentId="A" />);
    await act(async () => {});
    const oldAtoms = deferred();
    const oldEntities = deferred();
    mocks.atoms.mockReturnValueOnce(oldAtoms.promise).mockResolvedValueOnce({
      items: [makeAtom({ assertion: "new atom" })],
      total: 1,
    });
    mocks.entities
      .mockReturnValueOnce(oldEntities.promise)
      .mockResolvedValueOnce({
        items: [makeEntity({ canonical_name: "new entity" })],
      });
    await act(async () => {
      mocks.createProps!.onSuccess();
      mocks.createProps!.onSuccess();
    });
    await act(async () => {
      oldAtoms.resolve({
        items: [makeAtom({ assertion: "old atom" })],
        total: 1,
      });
      oldEntities.resolve({
        items: [makeEntity({ canonical_name: "old entity" })],
      });
    });
    expect(screen.getByText("new atom")).toBeInTheDocument();
    expect(screen.getByTestId("entities")).toHaveTextContent(/^new entity$/);
  });

  it("clears the selected atom and create modal, and ignores callbacks from a prior A visit", async () => {
    mocks.atoms.mockResolvedValue({
      items: [makeAtom({ assertion: "visible atom" })],
      total: 1,
    });
    const { rerender } = render(<AtomsList agentId="A" />);
    await act(async () => {});
    fireEvent.click(screen.getByText("visible atom"));
    fireEvent.click(screen.getByRole("button", { name: "编辑这条记忆" }));
    const editSuccess = mocks.edit.mock.calls[0][0].onSuccess;
    const oldCreateSuccess = mocks.createProps!.onSuccess;
    const oldCreateClose = mocks.createProps!.onClose;
    fireEvent.click(screen.getByRole("button", { name: "新建记忆" }));
    expect(mocks.createProps!.open).toBe(true);
    await act(async () => rerender(<AtomsList agentId="B" />));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mocks.createProps!.open).toBe(false);
    expect(mocks.destroyAction).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "新建记忆" }));
    act(() => oldCreateClose());
    expect(mocks.createProps!.open).toBe(true);
    await act(async () => rerender(<AtomsList agentId="A" />));
    const atomCalls = mocks.atoms.mock.calls.length;
    const entityCalls = mocks.entities.mock.calls.length;
    await act(async () => {
      editSuccess(makeAtom({ assertion: "obsolete edit" }));
      oldCreateSuccess();
    });
    expect(mocks.atoms).toHaveBeenCalledTimes(atomCalls);
    expect(mocks.entities).toHaveBeenCalledTimes(entityCalls);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("destroys the deprecation confirmation when the list unmounts", async () => {
    mocks.atoms.mockResolvedValue({
      items: [makeAtom({ assertion: "visible atom" })],
      total: 1,
    });
    const { unmount } = render(<AtomsList agentId="A" />);
    await act(async () => {});
    fireEvent.click(screen.getByText("visible atom"));
    fireEvent.click(screen.getByRole("button", { name: "弃用这条记忆" }));
    expect(mocks.deprecate).toHaveBeenCalledOnce();
    unmount();
    expect(mocks.destroyAction).toHaveBeenCalledOnce();
  });

  it("refreshes the current filter when an edit started under the previous filter completes", async () => {
    mocks.atoms.mockResolvedValue({
      items: [makeAtom({ assertion: "visible atom" })],
      total: 1,
    });
    render(<AtomsList agentId="A" />);
    await act(async () => {});
    fireEvent.click(screen.getByText("visible atom"));
    fireEvent.click(screen.getByRole("button", { name: "编辑这条记忆" }));
    const editSuccess = mocks.edit.mock.calls[0][0].onSuccess;
    await act(async () =>
      fireEvent.change(screen.getAllByRole("combobox")[0], {
        target: { value: "Fact" },
      }),
    );
    const calls = mocks.atoms.mock.calls.length;
    await act(async () => editSuccess(makeAtom()));
    expect(mocks.atoms).toHaveBeenCalledTimes(calls + 1);
    expect(mocks.atoms).toHaveBeenLastCalledWith(
      "A",
      expect.objectContaining({ candidate_type: "Fact" }),
    );
  });
});

describe("Candidate action completion", () => {
  it.each(["resolve", "reject"] as const)(
    "ignores obsolete promote %s after A/B/A",
    async (outcome) => {
      const pending = deferred();
      mocks.promote.mockReturnValue(pending.promise);
      mocks.candidates.mockResolvedValue({
        items: [makeCandidate()],
        total: 1,
      });
      const { rerender } = render(<CandidatesReview agentId="A" />);
      await act(async () => {});
      fireEvent.click(screen.getByText("confirm action"));
      await act(async () => rerender(<CandidatesReview agentId="B" />));
      await act(async () => rerender(<CandidatesReview agentId="A" />));
      const calls = mocks.candidates.mock.calls.length;
      await act(async () => {
        if (outcome === "resolve")
          pending.resolve({ merged: 0, promoted: 1, needs_review: 0 });
        else pending.reject(new Error("old promote"));
      });
      expect(mocks.candidates).toHaveBeenCalledTimes(calls);
      expect(mocks.success).not.toHaveBeenCalled();
      expect(mocks.error).not.toHaveBeenCalled();
    },
  );

  it("does not let A's rejection close B's pending rejection modal", async () => {
    const old = deferred();
    const current = deferred();
    mocks.reject
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(current.promise);
    mocks.candidates.mockResolvedValue({ items: [makeCandidate()], total: 1 });
    const { rerender } = render(<CandidatesReview agentId="A" />);
    await act(async () => {});
    fireEvent.click(screen.getByRole("button", { name: /忽\s*略/ }));
    fireEvent.click(screen.getByText("confirm reject"));
    await act(async () => rerender(<CandidatesReview agentId="B" />));
    expect(screen.queryByTestId("reject-modal")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /忽\s*略/ }));
    fireEvent.click(screen.getByText("confirm reject"));
    const calls = mocks.candidates.mock.calls.length;
    await act(async () => old.resolve({}));
    expect(screen.getByTestId("reject-modal")).toHaveAttribute(
      "data-loading",
      "true",
    );
    expect(mocks.candidates).toHaveBeenCalledTimes(calls);
    expect(mocks.success).not.toHaveBeenCalled();
    await act(async () => current.resolve({}));
    expect(screen.queryByTestId("reject-modal")).not.toBeInTheDocument();
    expect(mocks.candidates).toHaveBeenLastCalledWith("B", expect.anything());
  });

  it("finishes an in-agent rejection and refreshes the latest filter", async () => {
    const pending = deferred();
    mocks.reject.mockReturnValue(pending.promise);
    mocks.candidates.mockResolvedValue({ items: [makeCandidate()], total: 1 });
    render(<CandidatesReview agentId="A" />);
    await act(async () => {});
    fireEvent.click(screen.getByRole("button", { name: /忽\s*略/ }));
    fireEvent.click(screen.getByText("confirm reject"));
    await act(async () =>
      fireEvent.change(screen.getAllByRole("combobox")[0], {
        target: { value: "promoted" },
      }),
    );
    const calls = mocks.candidates.mock.calls.length;
    await act(async () => pending.resolve({}));
    expect(screen.queryByTestId("reject-modal")).not.toBeInTheDocument();
    expect(mocks.candidates).toHaveBeenCalledTimes(calls + 1);
    expect(mocks.candidates).toHaveBeenLastCalledWith(
      "A",
      expect.objectContaining({ status: "promoted" }),
    );
  });
});

describe("Conversation list actions", () => {
  it("clears the selection and desktop page on agent change; ignores the old delete", async () => {
    const pending = deferred();
    mocks.removeThread.mockReturnValue(pending.promise);
    mocks.threads.mockResolvedValue([
      {
        thread_id: "same-id",
        title: "visible thread",
        channel_type: "web",
        created_at: 1,
        last_active: 2,
      },
    ]);
    const { rerender } = render(<ConversationRecords agentId="A" />);
    await act(async () => {});
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "common.view" })),
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.click(screen.getByText("page 2"));
    expect(screen.getByTestId("page")).toHaveTextContent(/^2$/);
    fireEvent.click(screen.getByText("confirm action"));
    await act(async () => rerender(<ConversationRecords agentId="B" />));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByTestId("page")).toHaveTextContent(/^1$/);
    await act(async () => pending.resolve({}));
    expect(screen.getByText("visible thread")).toBeInTheDocument();
    expect(mocks.success).not.toHaveBeenCalled();
  });
});
