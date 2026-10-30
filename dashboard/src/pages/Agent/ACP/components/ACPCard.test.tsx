import { cleanup, render, screen } from "@testing-library/react";
import { createInstance } from "i18next";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ACPRunnerConfig } from "../../../../api/types/acp";
import en from "../../../../locales/en.json";
import zh from "../../../../locales/zh.json";
import { ACPCard } from "./ACPCard";

vi.unmock("react-i18next");

afterEach(cleanup);
const config: ACPRunnerConfig = {
  enabled: true,
  command: "my-agent",
  args: [],
  env: {},
  trusted: false,
  tool_parse_mode: "call_title",
  stdio_buffer_limit_bytes: 50 * 1024 * 1024,
};

async function show(lng: string, runnerKey: string, command = "my-agent") {
  const i18n = createInstance();
  await i18n.use(initReactI18next).init({
    lng,
    fallbackLng: "en",
    resources: { en: { translation: en }, zh: { translation: zh } },
    interpolation: { escapeValue: false },
  });
  render(
    <I18nextProvider i18n={i18n}>
      <ACPCard
        runnerKey={runnerKey}
        config={{ ...config, command }}
        isHover={false}
        onClick={vi.fn()}
        onMouseEnter={vi.fn()}
        onMouseLeave={vi.fn()}
        onToggleEnabled={vi.fn()}
      />
    </I18nextProvider>,
  );
}

describe("ACP runner card labels", () => {
  it.each([
    ["en", "Custom runner: my-agent"],
    ["zh", "自定义 Runner：my-agent"],
  ])(
    "shows the custom key and interpolated command in %s",
    async (lng, description) => {
      await show(lng, "local-agent");
      expect(screen.getByText("local-agent")).toBeInTheDocument();
      expect(
        screen.getByRole("img", { name: "local-agent" }),
      ).toBeInTheDocument();
      expect(screen.getByText(description)).toBeInTheDocument();
      expect(screen.queryByText("acp.runner_custom")).toBeNull();
      expect(screen.queryByText(/\{\{command\}\}/)).toBeNull();
    },
  );

  it.each(["en", "zh"])(
    "keeps the built-in title and description translated in %s",
    async (lng) => {
      await show(lng, "opencode");
      const copy = lng === "en" ? en.acp : zh.acp;
      expect(screen.getByText(copy.runner_opencode)).toBeInTheDocument();
      expect(screen.getByText(copy.intro_opencode)).toBeInTheDocument();
    },
  );

  it("uses the translated missing-command text for an unconfigured custom runner", async () => {
    await show("en", "unconfigured-agent", "");
    expect(
      screen.getByText(`Custom runner: ${en.acp.notSet}`),
    ).toBeInTheDocument();
  });
});
