import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { name?: string }) =>
      opts?.name ? `${key}:${opts.name}` : key,
  }),
}));

vi.mock("./iconForName", () => ({
  iconForName: () => <span data-testid="peer-icon" />,
}));

import EditExpertDrawerTitle from "./EditExpertDrawerTitle";

describe("EditExpertDrawerTitle", () => {
  it("places the peer icon and connection name after the title", () => {
    const { container } = render(
      <EditExpertDrawerTitle
        agent={{
          agent_id: "bridge:c1:doctor",
          bridge: true,
          bridge_connection_name: "云端实验室",
          bridge_connection_icon: "cloudy",
        }}
      />,
    );
    expect(screen.getByTestId("peer-icon")).toBeInTheDocument();
    expect(screen.getByText("云端实验室")).toBeInTheDocument();
    expect(screen.getByText("experts.editExpert")).toBeInTheDocument();
    expect(container.textContent).toMatch(
      /experts\.editExpert[\s\S]*云端实验室/,
    );
  });

  it("keeps the plain title for a local expert", () => {
    render(
      <EditExpertDrawerTitle agent={{ agent_id: "01LOCAL", bridge: false }} />,
    );
    expect(screen.getByText("experts.editExpert")).toBeInTheDocument();
    expect(screen.queryByTestId("peer-icon")).not.toBeInTheDocument();
  });
});
