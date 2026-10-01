import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import TeamMemberPicker, { selectedRosterIds } from "./TeamMemberPicker";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { name?: string }) =>
      key === "experts.share.fromOwner" ? `Shared by ${options?.name}` : key,
  }),
}));

const experts = [
  {
    agent_id: "a",
    name: "Alpha",
    kind: "expert",
    is_owner: true,
  },
  {
    agent_id: "b",
    name: "Beta",
    kind: "expert",
    is_owner: true,
  },
  {
    agent_id: "c",
    name: "Gamma",
    kind: "expert",
    is_owner: true,
  },
];

describe("TeamMemberPicker", () => {
  it("identifies and searches same-named shared experts by owner", () => {
    const onChange = vi.fn();
    render(
      <TeamMemberPicker
        experts={[
          { agent_id: "mine", name: "Writer", is_owner: true },
          {
            agent_id: "alice-writer",
            name: "Writer",
            is_shared: true,
            is_owner: false,
            owner_username: "Alice",
          },
          {
            agent_id: "bob-writer",
            name: "Writer",
            is_shared: true,
            is_owner: false,
            owner_username: "Bob",
          },
        ]}
        onChange={onChange}
      />,
    );
    expect(
      screen.getByRole("button", { name: /Shared by Alice/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Shared by Bob/ }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "alice" },
    });
    expect(screen.getAllByRole("button", { pressed: false })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: /Alice/ }));
    expect(onChange).toHaveBeenCalledWith(["alice-writer"]);
  });

  it("adds and removes members like create", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <TeamMemberPicker
        value={["a", "b"]}
        onChange={onChange}
        experts={experts}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Gamma/ }));
    expect(onChange).toHaveBeenCalledWith(["a", "b", "c"]);

    fireEvent.click(screen.getByRole("button", { name: /Alpha/ }));
    expect(onChange).toHaveBeenCalledWith(["b"]);

    rerender(
      <TeamMemberPicker
        value={["b", "missing"]}
        onChange={onChange}
        experts={experts}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Gamma/ }));
    expect(onChange).toHaveBeenLastCalledWith(["b", "c"]);
  });

  it("treats selection as one full roster, dropping unusable ids", () => {
    expect(
      selectedRosterIds(
        ["a", "missing", "other-team", "b", "a"],
        [
          ...experts,
          {
            agent_id: "other-team",
            name: "Nested",
            kind: "team",
            is_owner: true,
          },
        ],
      ),
    ).toEqual(["a", "b"]);
  });

  it("does not pick peer (cloud-collab) experts for a local team", () => {
    expect(
      selectedRosterIds(
        ["a", "bridge:c1:x", "b"],
        [
          ...experts,
          {
            agent_id: "bridge:c1:x",
            name: "Peer",
            kind: "expert",
            is_owner: true,
            bridge: true,
          },
        ],
      ),
    ).toEqual(["a", "b"]);
  });

  it("keeps the first-load order when toggling selection", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <TeamMemberPicker value={["c"]} onChange={onChange} experts={experts} />,
    );
    const names = () =>
      screen.getAllByRole("button").map((el) => el.textContent ?? "");
    expect(names()[0]).toMatch(/Gamma/);

    fireEvent.click(screen.getByRole("button", { name: /Alpha/ }));
    expect(onChange).toHaveBeenCalledWith(["c", "a"]);
    rerender(
      <TeamMemberPicker
        value={["c", "a"]}
        onChange={onChange}
        experts={experts}
      />,
    );
    expect(names()[0]).toMatch(/Gamma/);
  });
});
