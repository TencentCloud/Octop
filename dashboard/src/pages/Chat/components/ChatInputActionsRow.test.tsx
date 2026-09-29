import { fireEvent, render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { ResolvedModel } from "../../../api/types";
import ChatInputActionsRow from "./ChatInputActionsRow";

vi.mock("./ContextWindowRing", () => ({
  default: () => null,
}));

const models: ResolvedModel[] = [
  {
    provider_id: 1,
    provider_name: "Provider",
    provider_kind: "openai",
    model: "compact-model",
    name: "Compact Model",
    context_window: 128_000,
  },
];

describe("ChatInputActionsRow compact pickers", () => {
  it("uses a popover instead of a full-width drawer on narrow desktop", async () => {
    const { container } = render(
      <MemoryRouter>
        <ChatInputActionsRow
          isMobile={false}
          isStreaming={false}
          canSend={false}
          text=""
          polishing={false}
          uploading={false}
          recording={false}
          transcribing={false}
          availableModels={models}
          onModelChange={vi.fn()}
          slashPickerGroups={null}
          slashMenuItems={[]}
          onSlashShortcutSelect={vi.fn()}
          onFileSelect={vi.fn()}
          onNewChat={vi.fn()}
          onPolish={vi.fn()}
          onToggleVoice={vi.fn()}
          onCancel={vi.fn()}
          onSubmit={vi.fn()}
        />
      </MemoryRouter>,
    );

    const modelButton = container
      .querySelector("svg.lucide-cpu")
      ?.closest("button");
    expect(modelButton).not.toBeNull();
    expect(modelButton).not.toHaveTextContent("Auto");
    expect(modelButton).not.toHaveTextContent("Compact Model");
    expect(modelButton).not.toHaveTextContent("compact-model");

    fireEvent.click(modelButton!);

    await waitFor(() => {
      expect(document.querySelector(".ant-popover")).toBeInTheDocument();
    });
    const popover = document.querySelector(".ant-popover");
    // ★ 断言过时修复（批次十四 `T-B-CASES` 余项 · **依据**如下，非"更新期望值"）：
    //   `ChatInputActionsRow.tsx` 的 **模型** popover 内容 = `modelMenu`（@469），
    //   其条目图标是 `Route`（@491 一带）；本文件里的 `Sparkles` 只属于
    //   **抽屉** @650 与**技能**触发器 @1063 —— 从未属于模型 popover。
    //   ★ `L-4` 分离：本测试与组件自基线 `9b287890` **逐字未变**（`git diff --stat` 空）
    //     ⇒ 基线**同样红** ⇒ **不是实现回归**（(a)：断言与实现从未一致）。
    //   ★ 语义保持：仍断言"popover 里既有图标、又有图片"（两条都**保留**，只换成当前图标）。
    expect(popover?.querySelector("svg.lucide-route")).not.toBeNull();
    expect(popover?.querySelector("img")).not.toBeNull();
    expect(document.querySelector(".ant-drawer-content")).toBeNull();
  });
});
