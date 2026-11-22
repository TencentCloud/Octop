import { useState } from "react";
import { Button, Drawer, Form, Input } from "antd";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { expect, it, vi } from "vitest";
import FileEditModal from "../FileEditModal";
import ExpertSettingsDrawer from "./ExpertSettingsDrawer";

it("registers closed settings and restores unset and nested values on cancel", async () => {
  const onSave = vi.fn();
  render(
    <Drawer open title="Expert">
      <Form onFinish={onSave}>
        <ExpertSettingsDrawer
          title="Runtime"
          summary="Runtime options"
          fields={["limit", ["compaction", "ratio"]]}
        >
          <Form.Item name="limit" label="Limit">
            <Input />
          </Form.Item>
          <Form.Item
            name={["compaction", "ratio"]}
            label="Ratio"
            initialValue="0.5"
          >
            <Input />
          </Form.Item>
        </ExpertSettingsDrawer>
        <Button htmlType="submit">Save expert</Button>
      </Form>
    </Drawer>,
  );
  const main = screen.getByRole("dialog");
  const save = within(main).getByRole("button", { name: "Save expert" });
  fireEvent.click(save);
  await waitFor(() =>
    expect(onSave).toHaveBeenCalledWith({
      limit: undefined,
      compaction: { ratio: "0.5" },
    }),
  );

  const open = within(main).getByRole("button", { name: /Runtime options/ });
  fireEvent.click(open);
  const settings = within((await screen.findAllByRole("dialog"))[1]);
  fireEvent.change(settings.getByLabelText("Limit"), {
    target: { value: "9" },
  });
  fireEvent.change(settings.getByLabelText("Ratio"), {
    target: { value: "0.9" },
  });
  fireEvent.click(settings.getByRole("button", { name: "common.cancel" }));
  fireEvent.click(save);
  await waitFor(() => expect(onSave).toHaveBeenCalledTimes(2));
  expect(onSave).toHaveBeenLastCalledWith({
    limit: undefined,
    compaction: { ratio: "0.5" },
  });
});

it("pushes the settings drawer and returns to it when the file editor closes", async () => {
  function Fixture() {
    const [fileOpen, setFileOpen] = useState(false);
    return (
      <Drawer open title="Expert">
        <Form>
          <ExpertSettingsDrawer title="Files" summary="Configuration files">
            <Button onClick={() => setFileOpen(true)}>Edit action guide</Button>
            <FileEditModal
              open={fileOpen}
              filePath="/AGENTS.md"
              localValue="Keep this draft"
              onLocalSave={() => undefined}
              onSaved={() => undefined}
              onClose={() => setFileOpen(false)}
            />
          </ExpertSettingsDrawer>
        </Form>
      </Drawer>
    );
  }

  render(<Fixture />);
  fireEvent.click(screen.getByRole("button", { name: /Configuration files/ }));
  const settings = (await screen.findAllByRole("dialog"))[1];
  const settingsWrapper = settings.closest<HTMLElement>(
    ".ant-drawer-content-wrapper",
  );
  fireEvent.click(
    within(settings).getByRole("button", { name: "Edit action guide" }),
  );
  await waitFor(() => expect(screen.getAllByRole("dialog")).toHaveLength(3));
  expect(settingsWrapper?.style.transform).toContain("translateX(-180px)");

  const editor = screen.getAllByRole("dialog")[2];
  fireEvent.keyDown(editor, { key: "Escape", keyCode: 27 });
  await waitFor(() => expect(screen.getAllByRole("dialog")).toHaveLength(2));
  expect(
    within(settings).getByRole("button", { name: "Edit action guide" }),
  ).toBeVisible();
});
