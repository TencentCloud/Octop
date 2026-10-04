import { useState } from "react";
import { Drawer, Modal } from "antd";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import RetainedSurface from "./RetainedSurface";
function Editor({ kind }: { kind: "modal" | "drawer" }) {
  const [draft, setDraft] = useState("");
  const Frame = kind === "modal" ? Modal : Drawer;
  return (
    <Frame open title="Draft editor">
      <input
        aria-label="Draft"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
      />
    </Frame>
  );
}
describe("retained surface portals", () => {
  it.each(["modal", "drawer"] as const)(
    "hides inactive %s without discarding its draft",
    async (kind) => {
      const { rerender, unmount } = render(
        <RetainedSurface active>
          <Editor kind={kind} />
        </RetainedSurface>,
      );
      await userEvent.type(
        await screen.findByRole("textbox", { name: "Draft" }),
        "Unsaved draft",
      );
      rerender(
        <RetainedSurface active={false}>
          <Editor kind={kind} />
        </RetainedSurface>,
      );
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(document.querySelector(".wb-surface-portals")).toHaveAttribute(
        "hidden",
      );
      rerender(
        <RetainedSurface active>
          <Editor kind={kind} />
        </RetainedSurface>,
      );
      expect(screen.getByRole("textbox", { name: "Draft" })).toHaveValue(
        "Unsaved draft",
      );
      unmount();
      expect(document.querySelector(".wb-surface-portals")).toBeNull();
    },
  );
});
