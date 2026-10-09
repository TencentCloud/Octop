import { afterEach, expect, it, vi } from "vitest";
import ko from "./locales/ko.json";

vi.mock("./api/modules/i18n", () => ({
  i18nApi: {
    getToolLabels: vi.fn(async () => ({
      labels: { read_file: "Read file", plugin_tool: "Plugin tool" },
    })),
    getSkillLabels: vi.fn(async () => ({ labels: { title: "Skills" } })),
  },
}));

import i18n, {
  ensureLocaleBundle,
  initI18n,
  refreshServerLabels,
} from "./i18n";
import { applyUserLocale } from "./utils/locale";

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

it("switches to Korean with English fallback and preserves bundled labels", async () => {
  localStorage.setItem("octop:ui-locale", "en");
  vi.stubGlobal("BASE_URL", "");
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => ({ setup_required: false }),
    })),
  );
  await initI18n();
  await ensureLocaleBundle("zh");
  i18n.addResourceBundle("en", "translation", { fallbackProbe: "English" });
  i18n.addResourceBundle("zh", "translation", {
    fallbackProbe: "Chinese",
    legacyFallbackProbe: "Chinese fallback",
  });
  expect(i18n.t("legacyFallbackProbe")).toBe("Chinese fallback");
  await applyUserLocale("ko");
  await refreshServerLabels("ko");
  expect(i18n.language).toBe("ko");
  expect(document.documentElement.lang).toBe("ko");
  expect(localStorage.getItem("octop:ui-locale")).toBe("ko");
  expect(i18n.t("fallbackProbe")).toBe("English");
  expect(i18n.t("tools.read_file")).toBe(ko.tools.read_file);
  expect(i18n.t("skills.title")).toBe(ko.skills.title);
  expect(i18n.t("tools.plugin_tool")).toBe("Plugin tool");
  await applyUserLocale("en");
  expect(document.documentElement.lang).toBe("en");
  expect(i18n.t("legacyFallbackProbe")).toBe("Chinese fallback");
});
