import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import styles from "../../../pages/Chat/index.module.less";
import { builtinPluginHost } from "../host";
import { DefaultToolRenderer } from "./DefaultToolRenderer";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));

const base = {
  pluginId: "builtin",
  toolName: "read_file",
  displayName: "读取文件",
  status: "running" as const,
  isStreaming: true,
  host: builtinPluginHost,
};

describe("DefaultToolRenderer streaming chrome", () => {
  it("places the breathing dots to the right of the tool name and keeps status on the right", () => {
    render(<DefaultToolRenderer {...base} />);

    const name = screen.getByText("读取文件");
    const status = screen.getByText("Running");
    const dots = name.nextElementSibling;

    expect(dots).toHaveClass(styles.inlineToolLiveDots);
    expect(dots?.querySelectorAll("span")).toHaveLength(3);
    expect(dots?.contains(status)).toBe(false);
    expect(status).toHaveClass(styles.inlineToolStatus);
    expect(
      name.compareDocumentPosition(status) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      dots &&
        dots.compareDocumentPosition(status) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("shows the tool being called instead of the deferred wrapper name", () => {
    render(
      <DefaultToolRenderer
        {...base}
        toolName="call_deferred_tool"
        displayName="按需调用"
        status="done"
        isStreaming={false}
        args={{ name: "read_file", arguments: { file_path: "notes.txt" } }}
        output="ok"
      />,
    );

    expect(screen.getByText("read_file")).toBeInTheDocument();
    expect(screen.queryByText("按需调用")).not.toBeInTheDocument();
  });

  it("keeps the wrapper label until the deferred target name arrives", () => {
    render(
      <DefaultToolRenderer
        {...base}
        toolName="call_deferred_tool"
        displayName="按需调用"
        args={{}}
      />,
    );

    expect(screen.getByText("按需调用")).toBeInTheDocument();
  });

  it("keeps a completed status without the breathing dots", () => {
    render(
      <DefaultToolRenderer
        {...base}
        status="done"
        isStreaming={false}
        output="ok"
      />,
    );

    const name = screen.getByText("读取文件");
    const status = screen.getByText("Done");
    expect(name.nextElementSibling).toBe(status);
    expect(status).toHaveClass(styles.inlineToolStatus);
    expect(
      name.parentElement?.querySelector(`.${styles.inlineToolLiveDots}`),
    ).toBeNull();
  });
});
