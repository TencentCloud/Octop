import { createRef } from "react";
import { App, Drawer, Form, Input } from "antd";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import WelcomeConfig, { type WelcomeConfigRef } from "./WelcomeConfig";
import { normalizeQuickPrompts } from "./welcomeManifest";

const prompts = normalizeQuickPrompts([
  { title: { zh: "第一张", en: "First card" } },
  { title: { zh: "第二张", en: "Second card" } },
]);

describe("WelcomeConfig", () => {
  it("keeps the main form and previous card values until Done is applied", async () => {
    const ref = createRef<WelcomeConfigRef>();
    const onSave = vi.fn();
    render(
      <App>
        <Drawer open title="Edit expert">
          <Form
            initialValues={{
              name: "Initial name",
              welcome_message: "Initial title",
            }}
            onFinish={onSave}
          >
            <Form.Item name="name" label="Expert name">
              <Input />
            </Form.Item>
            <Form.Item name="welcome_message" noStyle>
              <WelcomeConfig ref={ref} initialPrompts={prompts} />
            </Form.Item>
            <button type="submit">Save expert</button>
          </Form>
        </Drawer>
      </App>,
    );
    const main = screen.getByRole("dialog");
    const name = within(main).getByLabelText("Expert name");
    fireEvent.change(name, { target: { value: "Edited name" } });
    const entry = within(main).getByRole("button", {
      name: /experts.pageConfigTitle/,
    });
    const openEditor = async () => {
      fireEvent.click(entry);
      return within((await screen.findAllByRole("dialog"))[1]);
    };

    const editWelcome = async () => {
      const editor = await openEditor();
      const welcome = editor.getByPlaceholderText(
        "experts.welcomeMessagePlaceholder",
      );
      expect(welcome).toHaveValue("Initial title");
      expect(
        editor.queryByPlaceholderText("experts.quickPromptTitlePlaceholder"),
      ).toBeNull();
      fireEvent.click(editor.getByRole("button", { name: "第二张" }));
      const card = editor.getByPlaceholderText(
        "experts.quickPromptTitlePlaceholder",
      );
      expect(card).toHaveValue("第二张");
      fireEvent.change(card, { target: { value: "已修改" } });
      fireEvent.change(welcome, { target: { value: "Edited title" } });
      return editor;
    };

    const firstEditor = await editWelcome();
    fireEvent.click(firstEditor.getByRole("button", { name: "common.cancel" }));
    expect(ref.current?.getSnapshot()).toEqual({
      status: "ready",
      dirty: false,
      data: { quick_prompts: prompts },
    });
    expect(name).toHaveValue("Edited name");

    const secondEditor = await editWelcome();
    fireEvent.click(
      secondEditor.getByRole("button", { name: "experts.configDone" }),
    );
    await waitFor(() => expect(ref.current?.getSnapshot().dirty).toBe(true));
    expect(onSave).not.toHaveBeenCalled();
    expect(ref.current?.getSnapshot().data.quick_prompts[1].title).toEqual({
      zh: "已修改",
      en: "Second card",
    });
    fireEvent.click(within(main).getByRole("button", { name: "Save expert" }));
    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({
        name: "Edited name",
        welcome_message: "Edited title",
      }),
    );
  });
});
