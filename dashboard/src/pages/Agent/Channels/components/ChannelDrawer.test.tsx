import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Form } from "antd";
import { FormItemForField } from "./ChannelDrawer";

afterEach(cleanup);

it.each(["switch", "text", "password", "textarea", "json"] as const)(
  "shows %s help only in a question tooltip",
  async (type) => {
    render(
      <Form>
        <FormItemForField
          field={{
            name: "test",
            label: "Setting",
            type,
            helpKey: "Plain plugin help",
          }}
        />
      </Form>,
    );
    expect(screen.queryByText("Plain plugin help")).not.toBeInTheDocument();
    const question = screen.getByRole("img", { name: "Setting: ?" });
    await userEvent.hover(question);
    expect(await screen.findByRole("tooltip")).toHaveTextContent(
      "Plain plugin help",
    );
  },
);
