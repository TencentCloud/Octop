import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Modal, type ModalFuncProps } from "antd";
import { makeAtom, makeEntity } from "../../../test/memoryFixtures";

const mocks = vi.hoisted(() => ({
  atoms: vi.fn(),
  entities: vi.fn(),
  replace: vi.fn(),
  deprecate: vi.fn(),
  create: vi.fn(),
  threads: vi.fn(),
  history: vi.fn(),
  remove: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
  loading: vi.fn(),
  closeLoading: vi.fn(),
  mobile: false,
  t: (key: string, fallback?: unknown) =>
    typeof fallback === "string" ? fallback : key,
}));

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: mocks.t }) }));
vi.mock("../../../i18n", () => ({ default: { t: mocks.t } }));
vi.mock("../../../utils/antdMessage", () => ({
  message: {
    error: mocks.error,
    success: mocks.success,
    loading: mocks.loading,
  },
}));
vi.mock("../../../hooks/useIsMobile", () => ({
  useIsMobile: () => mocks.mobile,
}));
vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "UTC",
}));
vi.mock("../../../api/modules/memoryDashboard", () => ({
  memoryDashboardApi: {
    listAtoms: mocks.atoms,
    listEntities: mocks.entities,
    replaceAtom: mocks.replace,
    deprecateAtom: mocks.deprecate,
    createAtom: mocks.create,
  },
  isAtomDeprecated: () => false,
}));
vi.mock("../../../api/modules/octopThreads", () => ({
  CHAT_HISTORY_PAGE_SIZE: 50,
  octopThreadsApi: {
    list: mocks.threads,
    history: mocks.history,
    delete: mocks.remove,
  },
}));
vi.mock("./shared/LineageStrip", () => ({ default: () => null }));
vi.mock("./shared/MemoryPipelineEmpty", () => ({ default: () => null }));
vi.mock("../../../components/Markdown/LazyMarkdown", () => ({
  default: () => null,
}));

// Keep the mutation helpers and conversation confirmation real: replacing them
// with callback-only mocks hides stale toasts and dialogs mounted outside the list.
import AtomsList from "./AtomsList";
import ConversationRecords from "./ConversationRecords";

let restoreConfirm: (() => void) | undefined;
const originalWidth = window.innerWidth;

function deferred() {
  let resolve!: (value: unknown) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.clearAllMocks();
  for (const mutation of [
    mocks.replace,
    mocks.deprecate,
    mocks.create,
    mocks.remove,
  ]) {
    mutation.mockReset();
  }
  mocks.mobile = false;
  mocks.atoms.mockResolvedValue({
    items: [makeAtom({ assertion: "visible atom" })],
    total: 1,
  });
  mocks.entities.mockResolvedValue({ items: [], total: 0 });
  mocks.threads.mockResolvedValue([
    {
      thread_id: "same-id",
      title: "visible conversation",
      channel_type: "web",
      created_at: 1,
      last_active: 2,
    },
  ]);
  mocks.history.mockResolvedValue({ messages: [], has_more: false });
  mocks.loading.mockReturnValue(mocks.closeLoading);
});

afterEach(async () => {
  cleanup();
  restoreConfirm?.();
  restoreConfirm = undefined;
  window.innerWidth = originalWidth;
  act(() => Modal.destroyAll());
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
});

async function openAtomAction(action: "edit" | "deprecate") {
  let confirmProps: ModalFuncProps | undefined;
  const destroy = vi.fn();
  const spy = vi.spyOn(Modal, "confirm").mockImplementation((props) => {
    confirmProps = props;
    return { destroy, update: vi.fn() };
  });
  restoreConfirm = () => spy.mockRestore();
  const view = render(<AtomsList agentId="A" />);
  fireEvent.click(await screen.findByText("visible atom"));
  fireEvent.click(
    await screen.findByRole("button", {
      name: action === "edit" ? "编辑这条记忆" : "弃用这条记忆",
    }),
  );
  expect(confirmProps).toBeDefined();
  return { ...view, confirm: () => confirmProps!.onOk?.(), destroy };
}

describe.each(["edit", "deprecate"] as const)(
  "%s with the real helper",
  (action) => {
    const mutation = action === "edit" ? mocks.replace : mocks.deprecate;

    it.each([
      ["switch", "resolve"],
      ["switch", "reject"],
      ["revisit", "resolve"],
      ["revisit", "reject"],
      ["unmount", "resolve"],
      ["unmount", "reject"],
    ])("ignores obsolete feedback after %s and %s", async (change, outcome) => {
      const pending = deferred();
      mutation.mockReturnValueOnce(pending.promise);
      const { rerender, unmount, confirm, destroy } = await openAtomAction(
        action,
      );
      const completion = Promise.resolve(confirm());
      expect(mutation).toHaveBeenCalledOnce();
      if (change === "unmount") unmount();
      else {
        await act(async () => rerender(<AtomsList agentId="B" />));
        if (change === "revisit")
          await act(async () => rerender(<AtomsList agentId="A" />));
      }
      expect(destroy).toHaveBeenCalledOnce();
      const calls = mocks.atoms.mock.calls.length;
      await act(async () => {
        if (outcome === "resolve") pending.resolve({ atom: makeAtom() });
        else pending.reject(new Error("old operation failed"));
        await completion;
      });
      expect(mocks.success).not.toHaveBeenCalled();
      expect(mocks.error).not.toHaveBeenCalled();
      expect(mocks.atoms).toHaveBeenCalledTimes(calls);
    });

    it.each(["resolve", "reject"])(
      "preserves current %s feedback",
      async (outcome) => {
        const error = new Error("current failure");
        if (outcome === "resolve")
          mutation.mockResolvedValue({ atom: makeAtom() });
        else mutation.mockRejectedValue(error);
        const { confirm } = await openAtomAction(action);
        const calls = mocks.atoms.mock.calls.length;
        await act(async () => {
          if (outcome === "resolve") await confirm();
          else await expect(confirm()).rejects.toThrow(error);
        });
        if (outcome === "resolve") {
          expect(mocks.success).toHaveBeenCalledOnce();
          expect(mocks.atoms).toHaveBeenCalledTimes(calls + 1);
        } else {
          expect(mocks.error).toHaveBeenCalledOnce();
          expect(mocks.atoms).toHaveBeenCalledTimes(calls);
        }
      },
    );
  },
);

describe("create atom", () => {
  it.each(["resolve", "reject"])(
    "ignores an old %s without closing the new form",
    async (outcome) => {
      const pending = deferred();
      mocks.create.mockReturnValueOnce(pending.promise);
      const { rerender } = render(<AtomsList agentId="A" />);
      await screen.findByText("visible atom");
      fireEvent.click(screen.getByRole("button", { name: "新建记忆" }));
      fireEvent.change(await screen.findByLabelText("主题名称"), {
        target: { value: "old topic" },
      });
      fireEvent.change(screen.getByLabelText("记忆内容"), {
        target: { value: "old assertion" },
      });
      fireEvent.click(screen.getByRole("button", { name: /保\s*存/ }));
      await waitFor(() => expect(mocks.create).toHaveBeenCalledOnce());
      await act(async () => rerender(<AtomsList agentId="B" />));
      await waitFor(() =>
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
      );
      fireEvent.click(screen.getByRole("button", { name: "新建记忆" }));
      await screen.findByRole("dialog");
      const calls = mocks.atoms.mock.calls.length;
      await act(async () => {
        if (outcome === "resolve")
          pending.resolve({
            atom: makeAtom(),
            entity: makeEntity(),
            created_entity: true,
          });
        else pending.reject(new Error("old create failed"));
      });
      expect(screen.getByRole("dialog")).toBeInTheDocument();
      expect(mocks.success).not.toHaveBeenCalled();
      expect(mocks.error).not.toHaveBeenCalled();
      expect(mocks.atoms).toHaveBeenCalledTimes(calls);
    },
  );
});

describe.each([false, true])("conversation deletion (mobile: %s)", (mobile) => {
  async function openDelete() {
    mocks.mobile = mobile;
    window.innerWidth = mobile ? 390 : 1200;
    const view = render(<ConversationRecords agentId="A" />);
    await screen.findByText("visible conversation");
    fireEvent.click(screen.getByRole("button", { name: "common.delete" }));
    await screen.findByRole("dialog");
    return view;
  }

  it.each(["switch", "unmount"])(
    "destroys the confirmation on %s",
    async (change) => {
      const { rerender, unmount } = await openDelete();
      if (change === "unmount") unmount();
      else await act(async () => rerender(<ConversationRecords agentId="B" />));
      await waitFor(() =>
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
      );
      expect(mocks.remove).not.toHaveBeenCalled();
    },
  );

  it.each(["resolve", "reject"])(
    "ignores stale delete %s after A/B/A",
    async (outcome) => {
      const pending = deferred();
      mocks.remove.mockReturnValueOnce(pending.promise);
      const { rerender } = await openDelete();
      fireEvent.click(
        screen.getByRole("button", { name: "chat.deleteSessionOnly" }),
      );
      await waitFor(() =>
        expect(mocks.remove).toHaveBeenCalledWith("A", "same-id", false),
      );
      await act(async () => rerender(<ConversationRecords agentId="B" />));
      await act(async () => rerender(<ConversationRecords agentId="A" />));
      await act(async () => {
        if (outcome === "resolve") pending.resolve({ compacted: false });
        else pending.reject(new Error("old delete failed"));
      });
      expect(screen.getByText("visible conversation")).toBeInTheDocument();
      expect(mocks.success).not.toHaveBeenCalled();
      expect(mocks.error).not.toHaveBeenCalled();
    },
  );

  it("keeps a current 409 confirmation open and allows retry with compact", async () => {
    mocks.remove.mockRejectedValueOnce(
      new Error(
        `Request failed: 409 Conflict - ${JSON.stringify({
          error: { code: "THREAD_TURN_ACTIVE", message: "Reply in progress" },
        })}`,
      ),
    );
    await openDelete();
    fireEvent.click(
      screen.getByRole("button", { name: "chat.deleteSessionOnly" }),
    );
    await waitFor(() =>
      expect(mocks.error).toHaveBeenCalledWith("apiErrors.THREAD_TURN_ACTIVE"),
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("visible conversation")).toBeInTheDocument();
    mocks.remove.mockResolvedValueOnce({ compacted: true });
    fireEvent.click(
      screen.getByRole("button", { name: "chat.deleteSessionAndCompact" }),
    );
    await waitFor(() =>
      expect(mocks.remove).toHaveBeenLastCalledWith("A", "same-id", true),
    );
    await waitFor(() =>
      expect(
        screen.queryByText("visible conversation"),
      ).not.toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(mocks.success).toHaveBeenCalledWith("chat.deleteSessionCompacted");
    expect(mocks.closeLoading).toHaveBeenCalledOnce();
  });
});
