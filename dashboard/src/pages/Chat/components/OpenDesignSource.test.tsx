import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import OpenDesignSource from "./OpenDesignSource";
import {
  openDesignApi,
  type DesignTask,
} from "../../../api/modules/openDesign";

vi.mock("../../../api/modules/openDesign", () => ({
  openDesignApi: { file: vi.fn(), edit: vi.fn(), search: vi.fn() },
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../context/ThemeContext", () => ({
  useTheme: () => ({ isDark: false }),
}));
vi.mock("@monaco-editor/react", () => ({ DiffEditor: () => <div>diff</div> }));
const task = {
  task_id: "task",
  project: "p",
  instance_id: "i",
  result: { entryFile: "index.html" },
} as DesignTask;

describe("OpenDesign source review", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(openDesignApi.file).mockResolvedValue({
      path: "index.html",
      content: "original",
      digest: "a".repeat(64),
      truncated: false,
    });
    vi.mocked(openDesignApi.edit).mockResolvedValue({
      path: "index.html",
      content: "edited",
      digest: "b".repeat(64),
      truncated: false,
    });
  });
  it("requires review of the current draft and saves with the read digest", async () => {
    render(<OpenDesignSource agentId="a" threadId="t" task={task} />);
    fireEvent.click(
      screen.getByRole("button", { name: "openDesignSource.title" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "openDesignSource.load" }),
    );
    const input = await screen.findByRole("textbox", {
      name: "openDesignSource.content",
    });
    const save = screen.getByRole("button", { name: "openDesignSource.save" });
    fireEvent.change(input, { target: { value: "draft" } });
    expect(save).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: "openDesignSource.review" }),
    );
    expect(save).toBeEnabled();
    fireEvent.change(input, { target: { value: "edited" } });
    expect(save).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: "openDesignSource.review" }),
    );
    fireEvent.click(save);
    await waitFor(() =>
      expect(openDesignApi.edit).toHaveBeenCalledWith("a", "t", "i", "p", {
        path: "index.html",
        digest: "a".repeat(64),
        content: "edited",
      }),
    );
  });
  it("does not allow editing partial reads", async () => {
    vi.mocked(openDesignApi.file).mockResolvedValue({
      path: "index.html",
      content: "partial",
      digest: "a".repeat(64),
      truncated: true,
    });
    render(<OpenDesignSource agentId="a" threadId="t" task={task} />);
    fireEvent.click(
      screen.getByRole("button", { name: "openDesignSource.title" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "openDesignSource.load" }),
    );
    expect(
      await screen.findByRole("textbox", { name: "openDesignSource.content" }),
    ).toHaveAttribute("readonly");
    expect(
      screen.getByRole("button", { name: "openDesignSource.review" }),
    ).toBeDisabled();
    expect(openDesignApi.edit).not.toHaveBeenCalled();
  });
});
