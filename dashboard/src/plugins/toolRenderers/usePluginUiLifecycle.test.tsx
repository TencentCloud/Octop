import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const load = vi.fn().mockResolvedValue(undefined);
const reset = vi.fn();
vi.mock("./loader", () => ({
  loadInstalledPluginUis: () => load(),
  resetPluginUiLoader: () => reset(),
}));
vi.mock("./ensureBuiltins", () => ({ ensureBuiltinToolRenderers: vi.fn() }));
vi.mock("./host", () => ({ setPluginUiToolContext: vi.fn() }));
vi.mock("../../api/modules/plugins", () => ({
  pluginsApi: { list: vi.fn().mockResolvedValue([]) },
}));

import { usePluginUiLifecycle } from "./usePluginToolUis";

function Layout() {
  usePluginUiLifecycle();
  return null;
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.restoreAllMocks());

describe("plugin UI lifecycle across layout mounts", () => {
  it("cleans up once on unmount, then sets up once after signing in again", async () => {
    const first = render(<Layout />);
    await vi.waitFor(() => expect(load).toHaveBeenCalledTimes(1));
    first.unmount();
    expect(reset).toHaveBeenCalledTimes(1);

    const second = render(<Layout />);
    await vi.waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    expect(reset).toHaveBeenCalledTimes(1);

    second.unmount();
    expect(reset).toHaveBeenCalledTimes(2);
  });
});
