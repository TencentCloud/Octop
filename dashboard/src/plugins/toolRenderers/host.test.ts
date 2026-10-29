import { afterEach, describe, expect, it, vi } from "vitest";
import { createPluginUiHost } from "./host";
import { setAuthToken } from "../../api/request";

vi.mock("../../pages/Chat/hooks/chatStore", () => ({}));
vi.mock("../../i18n", () => ({ default: { language: "zh" } }));

afterEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("plugin binary resources", () => {
  it.each([
    ["/", "", "/api"],
    ["/octop/", "", "/octop/api"],
    ["/octop/", "https://api.example.test", "https://api.example.test/api"],
  ])(
    "uses the configured API base %s / %s with both login modes",
    async (base, apiHost, expected) => {
      vi.stubEnv("BASE_URL", base);
      vi.stubGlobal("BASE_URL", apiHost);
      const path = "/plugins/simple-theme/ui/fonts/InterVariable.woff2";
      const fetcher = vi
        .fn()
        .mockImplementation(async () => new Response("font-bytes"));
      vi.stubGlobal("fetch", fetcher);
      for (const remember of [true, false]) {
        setAuthToken("test-token", remember);
        const blob = await createPluginUiHost("simple-theme").requestBlob(path);
        expect(await blob.text()).toBe("font-bytes");
        expect(fetcher).toHaveBeenLastCalledWith(
          expected + path,
          expect.objectContaining({
            headers: expect.objectContaining({
              Authorization: "Bearer test-token",
            }),
          }),
        );
      }
    },
  );
});
