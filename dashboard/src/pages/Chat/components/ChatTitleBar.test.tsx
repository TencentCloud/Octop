import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { modal } from "../../../utils/antdModal";
import ChatTitleBar from "./ChatTitleBar";
import type { Session } from "../hooks/useSessions";
import styles from "../index.module.less";

vi.mock("../../../utils/antdModal", () => ({
  modal: { confirm: vi.fn() },
}));

const session: Session = {
  id: "s1",
  name: "Weekly recap",
  threadId: "t1",
  updatedAt: null,
  channelType: "web",
};

const noop = vi.fn();

describe("ChatTitleBar", () => {
  it.each([
    ["短标题", "Weekly recap"],
    ["超长标题", "很长的会话标题".repeat(80)],
  ])("将%s与右侧常驻操作组分开", (_label, title) => {
    render(
      <ChatTitleBar
        session={session}
        title={title}
        onRename={noop}
        onPin={noop}
        onFork={noop}
        onDelete={noop}
      />,
    );

    const heading = screen.getByRole("heading", { name: title });
    const edit = screen.getByRole("button", { name: "common.edit" });
    const more = screen.getByRole("button", { name: "更多" });
    const actions = edit.parentElement;
    const left = heading.closest(`.${styles.chatTitleLeft}`);

    expect(actions).toHaveClass(styles.chatTitleActions);
    expect(actions).toContainElement(more);
    expect(actions?.parentElement).toHaveClass(styles.chatTitleBar);
    expect(actions?.previousElementSibling).toBe(left);
    expect(left).not.toContainElement(edit);
    expect(left).not.toContainElement(more);
    expect(heading).toHaveAttribute("title", title);
    expect(edit).toBeVisible();
    expect(more).toBeVisible();
  });

  it("通过样式约束保持右侧按钮贴边、常驻，以及标题省略", () => {
    const css = readFileSync(
      resolve(__dirname, "../index.module.less"),
      "utf8",
    );
    const titleBar = css.match(/^\.chatTitleBar \{[\s\S]*?^\}/m)?.[0];
    const left = css.match(/^\.chatTitleLeft \{[\s\S]*?^\}/m)?.[0];
    const actions = css.match(/^\.chatTitleActions \{[\s\S]*?^\}/m)?.[0];
    const button = css.match(/^\.chatTitleEditBtn \{[\s\S]*?^\}/m)?.[0];
    const title = css.match(/^\.chatTitleText \{[\s\S]*?^\}/m)?.[0];
    const input = css.match(/^\.chatTitleInput \{[\s\S]*?^\}/m)?.[0];

    expect(titleBar).toContain("display: flex");
    expect(titleBar).toContain("padding: 0 var(--chat-title-pad-x)");
    expect(titleBar).not.toContain("window-controls-inset-end");
    expect(css).not.toMatch(
      /\.chatTitleBar \{[^}]*window-controls-inset-end/,
    );
    expect(titleBar).not.toMatch(/^\s*max-width:|chatTitleEditBtn/m);
    expect(left).toContain("flex: 1");
    expect(left).toContain("min-width: 0");
    expect(left).not.toMatch(/max-width|margin:/);
    expect(actions).toContain("display: flex");
    expect(actions).toContain("flex-shrink: 0");
    expect(actions).not.toMatch(/opacity:\s*0|visibility:\s*hidden/);
    expect(button).not.toMatch(
      /opacity:\s*0|pointer-events:\s*none|visibility:\s*hidden/,
    );
    expect(css).not.toContain("chatTitleHoverShown");
    expect(title).toContain("min-width: 0");
    expect(title).toContain("text-overflow: ellipsis");
    expect(title).toContain("white-space: nowrap");
    expect(input).toContain("min-width: 0");
    const source = readFileSync(resolve(__dirname, "ChatTitleBar.tsx"), "utf8");
    expect(source).toContain('placement="bottomRight"');
  });

  it("leaves window dragging to the single bounded shell region", () => {
    const { container } = render(
      <ChatTitleBar
        session={session}
        title="Weekly recap"
        onRename={noop}
        onPin={noop}
        onFork={noop}
        onDelete={noop}
      />,
    );

    expect(container.querySelector(".octop-desktop-drag")).toBeNull();
  });

  it("shows the expert shared flag beside an owner's contributed title", () => {
    render(
      <ChatTitleBar
        session={{ ...session, contributed: true, owned: true }}
        title="Weekly recap"
        onRename={noop}
        onPin={noop}
        onFork={noop}
        onDelete={noop}
      />,
    );

    const heading = screen.getByRole("heading", { name: "Weekly recap" });
    const badge = screen.getByTitle(/sharedResource\.shared|已共享|Shared/);
    const more = screen.getByRole("button", { name: "更多" });
    expect(heading.compareDocumentPosition(badge)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(badge.compareDocumentPosition(more)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it("shows only a share icon for a session shared with the viewer", () => {
    render(
      <ChatTitleBar
        session={{ ...session, contributed: true, owned: false }}
        title="Weekly recap"
        onRename={noop}
        onPin={noop}
        onFork={noop}
        onDelete={noop}
      />,
    );

    const mark = screen.getByLabelText("chat.sharedSession");
    expect(mark.querySelector("svg")).not.toBeNull();
    expect(mark).not.toHaveTextContent(/已共享|Shared|sharedResource/);
  });

  it("shows a team badge next to the title for group chats", () => {
    render(
      <ChatTitleBar
        session={session}
        title="Weekly recap"
        onRename={noop}
        onPin={noop}
        onFork={noop}
        onDelete={noop}
        isTeam
      />,
    );

    expect(screen.getByLabelText("chat.teamBadge")).toBeInTheDocument();
  });

  it("shows the cloud flag next to a remote conversation title", () => {
    render(
      <ChatTitleBar
        session={session}
        title="Weekly recap"
        onRename={noop}
        onPin={noop}
        onFork={noop}
        onDelete={noop}
        isTeam
        agent={{
          bridge: true,
          bridge_connection_name: "云端实验室",
          bridge_connection_icon: "cloudy",
        }}
      />,
    );

    const flag = screen.getByLabelText(/Peer expert|对端专家|remoteExpert/);
    expect(flag.querySelector("svg")).not.toBeNull();
    expect(screen.getByText("云端实验室")).toBeInTheDocument();
  });

  it("keeps icon and fallback text when the connection name is empty", () => {
    render(
      <ChatTitleBar
        session={session}
        title="Weekly recap"
        onRename={noop}
        onPin={noop}
        onFork={noop}
        onDelete={noop}
        agent={{ bridge: true }}
      />,
    );

    const flag = screen.getByLabelText(/Peer expert|对端专家|remoteExpert/);
    expect(flag.querySelector("svg")).not.toBeNull();
    expect(flag).toHaveTextContent(/对端|Peer|remoteExpert\.flag/);
  });

  it("编辑时保留操作组，禁用重复编辑，并可失焦保存后打开更多菜单", async () => {
    const user = userEvent.setup();
    const onRename = vi.fn();
    render(
      <ChatTitleBar
        session={session}
        title="Weekly recap"
        onRename={onRename}
        onPin={noop}
        onFork={noop}
        onDelete={noop}
      />,
    );

    const edit = screen.getByRole("button", { name: "common.edit" });
    const more = screen.getByRole("button", { name: "更多" });
    const actions = edit.parentElement;
    await user.click(edit);
    const input = screen.getByRole("textbox");
    expect(input).toHaveFocus();
    expect(edit).toBeDisabled();
    expect(edit).toBeVisible();
    expect(more).toBeEnabled();
    expect(more).toBeVisible();
    expect(actions).toContainElement(edit);
    expect(actions).toContainElement(more);
    expect(actions).not.toContainElement(input);

    fireEvent.change(input, { target: { value: "  Renamed recap  " } });
    await user.click(edit);
    expect(screen.getByRole("textbox")).toBe(input);
    expect(onRename).not.toHaveBeenCalled();

    await user.click(more);
    expect(onRename).toHaveBeenCalledExactlyOnceWith("s1", "Renamed recap");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(edit).toBeEnabled();
    await waitFor(() =>
      expect(screen.getByRole("menuitem", { name: "置顶" })).toBeVisible(),
    );
    expect(screen.getByRole("menuitem", { name: "分叉" })).toBeVisible();
    expect(
      screen.getByRole("menuitem", { name: "common.delete" }),
    ).toBeVisible();
    expect(
      screen.getByRole("switch", { name: "chat.collapseThinking" }),
    ).toBeVisible();
  });

  it("按 Enter 保存去除首尾空白的新标题", () => {
    const onRename = vi.fn();
    render(
      <ChatTitleBar
        session={session}
        title="Weekly recap"
        onRename={onRename}
        onPin={noop}
        onFork={noop}
        onDelete={noop}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "common.edit" }));
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "  Renamed recap  " } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onRename).toHaveBeenCalledExactlyOnceWith("s1", "Renamed recap");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "common.edit" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "更多" })).toBeVisible();
  });

  it("按 Escape 取消重命名并保留操作组", () => {
    const onRename = vi.fn();
    render(
      <ChatTitleBar
        session={session}
        title="Weekly recap"
        onRename={onRename}
        onPin={noop}
        onFork={noop}
        onDelete={noop}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "common.edit" }));
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "Cancelled recap" } });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onRename).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Weekly recap" })).toBeVisible();
    expect(screen.getByRole("button", { name: "更多" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "common.edit" }));
    expect(screen.getByRole("textbox")).toHaveValue("Weekly recap");
  });

  it.each([false, true])("更多菜单保留置顶切换：pinned=%s", async (pinned) => {
    const onPin = vi.fn();
    render(
      <ChatTitleBar
        session={{ ...session, pinned }}
        title="Weekly recap"
        onRename={noop}
        onPin={onPin}
        onFork={noop}
        onDelete={noop}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "更多" }));
    fireEvent.click(
      await screen.findByRole("menuitem", {
        name: pinned ? "取消置顶" : "置顶",
      }),
    );
    expect(onPin).toHaveBeenCalledExactlyOnceWith("s1", !pinned);
  });

  it.each([false, true])(
    "更多菜单保留分叉及禁用提示：disabled=%s",
    async (disabled) => {
      const onFork = vi.fn();
      render(
        <ChatTitleBar
          session={session}
          title="Weekly recap"
          onRename={noop}
          onPin={noop}
          onFork={onFork}
          onDelete={noop}
          forkDisabled={disabled}
          forkDisabledHint="当前不可分叉"
        />,
      );

      fireEvent.click(screen.getByRole("button", { name: "更多" }));
      const fork = await screen.findByRole("menuitem", { name: "分叉" });
      fireEvent.click(fork);
      if (disabled) {
        expect(fork).toHaveAttribute("aria-disabled", "true");
        expect(fork).toHaveAttribute("title", "当前不可分叉");
        expect(onFork).not.toHaveBeenCalled();
      } else {
        expect(onFork).toHaveBeenCalledExactlyOnceWith("s1");
      }
    },
  );

  it.each([false, true])(
    "更多菜单删除前要求确认：compact=%s",
    async (compact) => {
      const onDelete = vi.fn().mockResolvedValue(true);
      const destroy = vi.fn();
      vi.mocked(modal.confirm).mockImplementationOnce((config) => {
        render(<>{config.footer as ReactNode}</>);
        return { destroy } as ReturnType<typeof modal.confirm>;
      });
      render(
        <ChatTitleBar
          session={session}
          title="Weekly recap"
          onRename={noop}
          onPin={noop}
          onFork={noop}
          onDelete={onDelete}
        />,
      );

      fireEvent.click(screen.getByRole("button", { name: "更多" }));
      fireEvent.click(
        await screen.findByRole("menuitem", { name: "common.delete" }),
      );
      expect(
        screen.getByRole("button", { name: "common.cancel" }),
      ).toBeVisible();
      expect(onDelete).not.toHaveBeenCalled();
      fireEvent.click(
        screen.getByRole("button", {
          name: compact
            ? "chat.deleteSessionAndCompact"
            : "chat.deleteSessionOnly",
        }),
      );
      await waitFor(() =>
        expect(onDelete).toHaveBeenCalledExactlyOnceWith("s1", compact),
      );
      await waitFor(() => expect(destroy).toHaveBeenCalledOnce());
    },
  );

  it("waits for the IME to finish before committing a rename", () => {
    const onRename = vi.fn();
    render(
      <ChatTitleBar
        session={session}
        title="Weekly recap"
        onRename={onRename}
        onPin={noop}
        onFork={noop}
        onDelete={noop}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "common.edit" }));
    const input = screen.getByDisplayValue("Weekly recap");
    fireEvent.change(input, { target: { value: "周报 zhou" } });

    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    fireEvent.keyDown(input, { key: "Enter", keyCode: 229 });
    expect(onRename).not.toHaveBeenCalled();

    fireEvent.keyDown(input, { key: "Enter", keyCode: 13 });
    expect(onRename).toHaveBeenCalledWith("s1", "周报 zhou");
  });
});
