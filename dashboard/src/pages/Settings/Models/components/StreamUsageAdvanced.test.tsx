import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Form } from "antd";
import { describe, expect, it } from "vitest";
import { StreamUsageAdvanced } from "./StreamUsageAdvanced";

function renderFold() {
  return render(
    <Form initialValues={{ stream_usage: true }}>
      <StreamUsageAdvanced />
    </Form>,
  );
}

describe("StreamUsageAdvanced", () => {
  it("stays collapsed by default and keeps the form field mounted", async () => {
    const user = userEvent.setup();
    renderFold();

    expect(
      screen.getByRole("button", { name: "models.compatibility" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("models.streamUsage")).not.toBeVisible();

    await user.click(
      screen.getByRole("button", { name: "models.compatibility" }),
    );
    expect(screen.getByText("models.streamUsage")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "models.hideCompatibility" }),
    ).toBeInTheDocument();
  });
});
