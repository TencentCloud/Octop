import { beforeAll, describe, expect, it } from "vitest";
import i18n, { applyDesktopLocale, initDesktopI18n } from "./i18n";
import { statusText } from "./statusText";

// The shell copy must resolve from the page bundles, so this file asserts
// against the real i18next instance (the jsdom setup mocks react-i18next's
// hook, which would only echo the key).
describe("desktop shell status copy", () => {
  beforeAll(async () => {
    await initDesktopI18n();
  });

  it("renders a port conflict in both locales", async () => {
    const status = {
      code: "error.port_in_use",
      level: "error" as const,
      args: { port: 8088 },
    };

    await applyDesktopLocale("zh");
    expect(statusText(i18n.getFixedT("zh"), status)).toBe(
      "端口 8088 已被占用，通常是另一个 Octop 实例或其他程序。请先关闭它，或在客户端设置中改用其他端口。",
    );

    await applyDesktopLocale("en");
    expect(statusText(i18n.getFixedT("en"), status)).toBe(
      "Port 8088 is already in use, by another Octop instance or a different program. Close it, or set a different port in the desktop settings.",
    );
  });

  it("composes the health timeout copy with a localized duration", async () => {
    const status = {
      code: "health.not_ready_connect",
      level: "error" as const,
      args: { addr: "http://127.0.0.1:8088", seconds: 60 },
    };

    await applyDesktopLocale("zh");
    expect(statusText(i18n.getFixedT("zh"), status)).toBe(
      "Octop 服务未在1 分钟内就绪（http://127.0.0.1:8088）。目前无法连接该地址，请确认 Octop 正在运行。",
    );

    await applyDesktopLocale("en");
    expect(
      statusText(i18n.getFixedT("en"), {
        ...status,
        args: { addr: "http://127.0.0.1:8088", seconds: 120 },
      }),
    ).toBe(
      "Octop did not become ready within 2 minutes (http://127.0.0.1:8088). Could not connect — make sure Octop is running.",
    );
  });

  it("falls back to the raw code when a bundle has no copy yet", async () => {
    await applyDesktopLocale("en");
    expect(
      statusText(i18n.getFixedT("en"), {
        code: "error.not_in_the_bundle",
        level: "error",
        args: {},
      }),
    ).toBe("error.not_in_the_bundle");
  });
});
