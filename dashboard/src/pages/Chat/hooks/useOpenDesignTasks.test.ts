import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import {
  openDesignApi,
  type DesignTask,
} from "../../../api/modules/openDesign";
import { useOpenDesignTasks } from "./useOpenDesignTasks";

vi.mock("../../../api/modules/openDesign", () => ({
  openDesignApi: { watch: vi.fn() },
}));

it("shares one subscription and rejects late updates from the previous conversation", async () => {
  const calls: {
    notify: (tasks: DesignTask[]) => void;
    signal: AbortSignal;
  }[] = [];
  vi.mocked(openDesignApi.watch).mockImplementation(
    async (_agent, _thread, notify, signal) => {
      calls.push({ notify, signal });
      await new Promise<void>((resolve) =>
        signal.addEventListener("abort", () => resolve()),
      );
    },
  );
  const first = { task_id: "first" } as DesignTask;
  const second = { task_id: "second" } as DesignTask;
  const { result, rerender, unmount } = renderHook(
    ({ thread }) => useOpenDesignTasks("a", thread),
    { initialProps: { thread: "t1" } },
  );
  await waitFor(() => expect(calls).toHaveLength(1));
  act(() => calls[0].notify([first]));
  const oldRefresh = result.current.setTasks;
  expect(result.current.tasks).toEqual([first]);
  rerender({ thread: "t2" });
  expect(result.current.tasks).toEqual([]);
  await waitFor(() => expect(calls).toHaveLength(2));
  expect(calls[0].signal.aborted).toBe(true);
  act(() => calls[1].notify([second]));
  act(() => {
    calls[0].notify([first]);
    oldRefresh([first]);
  });
  expect(result.current.tasks).toEqual([second]);
  expect(calls).toHaveLength(2);
  unmount();
  expect(calls[1].signal.aborted).toBe(true);
});
