import { act, fireEvent, render, screen } from "@testing-library/react";
import type { TFunction } from "i18next";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { octopThreadsApi } from "../../../api/modules/octopThreads";
import { message } from "../../../utils/antdMessage";
import { modal } from "../../../utils/antdModal";
import {
  confirmDeleteConversation,
  deleteConversation,
} from "./deleteConversation";

vi.mock("../../../utils/antdModal", () => ({
  modal: { confirm: vi.fn() },
}));

vi.mock("../../../utils/antdMessage", () => ({
  message: {
    error: vi.fn(),
    success: vi.fn(),
    loading: vi.fn(() => undefined),
  },
}));

vi.mock("../../../api/modules/octopThreads", () => ({
  octopThreadsApi: { delete: vi.fn() },
}));

const TURN_ACTIVE =
  "A reply is still in progress. Stop it, then delete this conversation.";

const t = ((key: string) =>
  key === "apiErrors.THREAD_TURN_ACTIVE" ? TURN_ACTIVE : key) as TFunction;

const confirmMock = vi.mocked(modal.confirm);
const errorMock = vi.mocked(message.error);
const deleteMock = vi.mocked(octopThreadsApi.delete);

function turnActiveError(): Error {
  return new Error(
    `Request failed: 409 Conflict - ${JSON.stringify({
      error: { code: "THREAD_TURN_ACTIVE", message: TURN_ACTIVE },
    })}`,
  );
}

function openDialog(
  onConfirm: (compact: boolean) => Promise<boolean | null | void>,
): ReturnType<typeof vi.fn> {
  const destroy = vi.fn();
  confirmMock.mockImplementation((config) => {
    render(<>{config.footer as ReactNode}</>);
    return { destroy } as ReturnType<typeof modal.confirm>;
  });
  confirmDeleteConversation(t, onConfirm);
  return destroy;
}

describe("confirmDeleteConversation", () => {
  beforeEach(() => {
    confirmMock.mockReset();
    errorMock.mockReset();
    deleteMock.mockReset();
  });

  it("keeps the dialog open when delete returns 409 THREAD_TURN_ACTIVE", async () => {
    deleteMock.mockRejectedValue(turnActiveError());
    const destroy = openDialog((compact) =>
      deleteConversation("agent-a", "thr_1", compact, t),
    );

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "chat.deleteSessionOnly" }),
      );
    });

    expect(deleteMock).toHaveBeenCalledWith("agent-a", "thr_1", false);
    expect(errorMock).toHaveBeenCalledWith(TURN_ACTIVE);
    expect(destroy).not.toHaveBeenCalled();
  });

  it("closes the dialog after a successful delete", async () => {
    deleteMock.mockResolvedValue({ compacted: false, scheduled: true });
    const destroy = openDialog((compact) =>
      deleteConversation("agent-a", "thr_1", compact, t),
    );

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "chat.deleteSessionOnly" }),
      );
    });

    expect(destroy).toHaveBeenCalledOnce();
  });
});
