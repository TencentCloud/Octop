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

it.each([
  [
    "reply_broadcast",
    "channels.slackReplyBroadcast",
    "channels.slackReplyBroadcastHelp",
    ["off"],
  ],
  [
    "provider",
    "channels.whatsappProvider",
    "channels.whatsappProviderHelp",
    ["cloud"],
  ],
] as const)(
  "shows %s help only in a question tooltip",
  async (name, label, helpKey, options) => {
    render(
      <Form>
        <FormItemForField
          helpInTooltip
          field={{
            name,
            label,
            type: "select",
            options: [...options],
            helpKey,
          }}
        />
      </Form>,
    );
    expect(screen.queryByText(helpKey)).not.toBeInTheDocument();
    await userEvent.hover(screen.getByRole("img", { name: `${label}: ?` }));
    expect(await screen.findByRole("tooltip")).toHaveTextContent(helpKey);
  },
);

it("keeps other builtin field help under the control", () => {
  render(
    <Form>
      <FormItemForField
        field={{
          name: "allow_all_channels",
          label: "channels.discordAllowAllChannels",
          type: "switch",
          helpKey: "channels.discordAllowAllChannelsHelp",
        }}
      />
    </Form>,
  );
  expect(
    screen.getByText("channels.discordAllowAllChannelsHelp"),
  ).toBeInTheDocument();
  expect(screen.queryByRole("img", { name: /: \?$/ })).not.toBeInTheDocument();
});
