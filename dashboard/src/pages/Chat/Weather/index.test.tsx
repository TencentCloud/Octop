import { act, render, screen } from "@testing-library/react";
import { createInstance } from "i18next";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { describe, expect, it, vi } from "vitest";
import en from "../../../locales/en.json";
import zh from "../../../locales/zh.json";
import Weather from "./index";

vi.unmock("react-i18next");
vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "Asia/Shanghai",
}));

async function renderWeather(language: string, weather: string) {
  const i18n = createInstance();
  await i18n.use(initReactI18next).init({
    lng: language,
    fallbackLng: "en",
    resources: { en: { translation: en }, zh: { translation: zh } },
    interpolation: { escapeValue: false },
  });
  const output = JSON.stringify(
    JSON.stringify([
      { location: "Shanghai", weather, temperature: 23, date: "2026-10-17" },
    ]),
  );
  render(
    <I18nextProvider i18n={i18n}>
      <Weather
        data={{ content: [{ data: { output: "" } }, { data: { output } }] }}
      />
    </I18nextProvider>,
  );
  return i18n;
}

describe("Weather language", () => {
  it.each([
    ["en", "sunny", "Sunny"],
    ["en", "rainy", "Rainy"],
    ["en", "cloudy", "Cloudy"],
    ["zh", "sunny", "晴朗"],
    ["zh", "rainy", "雨天"],
    ["zh", "cloudy", "多云"],
  ])("renders %s %s as %s", async (language, weather, label) => {
    await renderWeather(language, weather);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("updates the condition when the interface language changes", async () => {
    const i18n = await renderWeather("en", "sunny");
    expect(screen.getByText("Sunny")).toBeInTheDocument();

    await act(async () => {
      await i18n.changeLanguage("zh");
    });

    expect(screen.getByText("晴朗")).toBeInTheDocument();
    expect(screen.queryByText("Sunny")).not.toBeInTheDocument();
  });

  it("preserves an unknown condition", async () => {
    await renderWeather("en", "snowy");
    expect(screen.getByText("snowy")).toBeInTheDocument();
  });
});
