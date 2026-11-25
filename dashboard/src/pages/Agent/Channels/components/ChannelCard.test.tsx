import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ChannelCard } from "./ChannelCard";
import { replacePluginChannelKinds, type ChannelKey } from "./constants";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));

afterEach(() => {
  cleanup();
  replacePluginChannelKinds([]);
});

it("renders the plugin description and exact icon, then falls back to the label when absent", () => {
  const entry = {
    kind: "acme",
    label: "Acme",
    icon: "data:image/svg+xml;base64,PHN2Zy8+",
    intro_url: "",
    plugin_id: "acme",
    description: "Connect Acme conversations",
  };
  const props = {
    channelKey: "acme" as ChannelKey,
    enabled: false,
    hasChannel: false,
    isHover: false,
    onClick: vi.fn(),
    onMouseEnter: vi.fn(),
    onMouseLeave: vi.fn(),
    onToggleEnabled: vi.fn(),
  };
  replacePluginChannelKinds([entry]);
  const { rerender } = render(<ChannelCard {...props} />);
  expect(screen.getByText(entry.description)).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Acme" })).toHaveAttribute(
    "src",
    entry.icon,
  );
  replacePluginChannelKinds([{ ...entry, description: "" }]);
  rerender(<ChannelCard {...props} />);
  expect(screen.queryByText(entry.description)).not.toBeInTheDocument();
  expect(screen.getAllByText("Acme")).toHaveLength(2);
});
