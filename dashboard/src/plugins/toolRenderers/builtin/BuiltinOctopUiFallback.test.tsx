import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import zh from "../../../locales/zh.json";
import { builtinPluginHost } from "../host";
import { BuiltinOctopUiFallback } from "./BuiltinOctopUiFallback";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const chat = zh.chat as Record<string, string>;
      const short = key.replace(/^chat\./, "");
      return chat[short] ?? key;
    },
  }),
}));

const base = {
  pluginId: "builtin",
  toolName: "get_weather",
  status: "done" as const,
  args: { city: "北京" },
  data: { city: "北京", current: { temp: 18.7 } },
  textFallback: "☁️ 北京 · 阴 18.7°C",
  host: builtinPluginHost,
  isStreaming: false,
};

describe("BuiltinOctopUiFallback", () => {
  it("shows the returned text and a local-install note for a missing remote plugin", () => {
    render(<BuiltinOctopUiFallback {...base} annotateMissingPlugin />);
    expect(
      screen.getByText("本机未安装该插件，仅展示数据"),
    ).toBeInTheDocument();
    expect(screen.getByText("☁️ 北京 · 阴 18.7°C")).toBeInTheDocument();
    expect(screen.queryByText(/"temp"/)).not.toBeInTheDocument();
  });

  it("keeps the structured dump when the plugin UI is simply not registered yet", () => {
    render(<BuiltinOctopUiFallback {...base} />);
    expect(
      screen.queryByText("本机未安装该插件，仅展示数据"),
    ).not.toBeInTheDocument();
    expect(screen.getByText('{"temp":18.7}')).toBeInTheDocument();
  });
});
