import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MagpieServerNotice } from "./MagpieServerNotice";

const discoverMagpie = vi.fn();

vi.mock("../../../../api/modules/magpie", () => ({
  discoverMagpie: (...args: unknown[]) => discoverMagpie(...args),
}));

describe("MagpieServerNotice", () => {
  beforeEach(() => {
    discoverMagpie.mockReset();
  });

  it("does not probe until the user checks", async () => {
    const user = userEvent.setup();
    discoverMagpie.mockResolvedValue({
      available: false,
      base_url: "http://127.0.0.1:3425/v1",
      version: null,
    });
    render(
      <App>
        <MagpieServerNotice />
      </App>,
    );

    expect(discoverMagpie).not.toHaveBeenCalled();
    expect(screen.getByText("models.magpieDiscoveryTitle")).toBeInTheDocument();
    expect(screen.getByText("models.magpieFailoverNote")).toBeInTheDocument();
    expect(screen.queryByText("models.magpieDiscoveryMissing")).toBeNull();

    await user.click(
      screen.getByRole("button", { name: "models.magpieCheck" }),
    );

    expect(discoverMagpie).toHaveBeenCalledOnce();
    expect(
      await screen.findByText("models.magpieDiscoveryMissing"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "models.magpieRescan" }),
    ).toBeInTheDocument();
  });

  it("shows a reachable Magpie after a manual check", async () => {
    const user = userEvent.setup();
    discoverMagpie.mockResolvedValue({
      available: true,
      base_url: "http://127.0.0.1:3425/v1",
      version: "1.2.3",
    });
    render(
      <App>
        <MagpieServerNotice />
      </App>,
    );

    await user.click(
      screen.getByRole("button", { name: "models.magpieCheck" }),
    );

    expect(
      await screen.findByText("models.magpieDiscoveryFound"),
    ).toBeInTheDocument();
    expect(screen.queryByText("models.magpieDiscoveryMissing")).toBeNull();
  });
});
