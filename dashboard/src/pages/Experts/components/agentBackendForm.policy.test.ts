import { describe, expect, it } from "vitest";
import {
  defaultCreateBackendChoice,
  resolveCreateBackendChoice,
  resolveRestrictedCompositeDefault,
} from "./agentBackendForm";

describe("expert backend allow-list", () => {
  it("keeps local_shell when the user is unrestricted or it is allowed", () => {
    expect(defaultCreateBackendChoice(null)).toBe("local_shell");
    expect(defaultCreateBackendChoice(undefined)).toBe("local_shell");
    expect(defaultCreateBackendChoice([])).toBe("local_shell");
    expect(defaultCreateBackendChoice(["cos", "local_shell"])).toBe(
      "local_shell",
    );
  });

  it("uses composite when local_shell is outside the allow-list", () => {
    expect(defaultCreateBackendChoice(["cos", "s3"])).toBe("composite");
  });

  it("replaces a disallowed local_shell and then prefers a loaded backend", () => {
    expect(
      resolveCreateBackendChoice("local_shell", [], {
        backendsLoading: true,
        userTouched: false,
      }),
    ).toBe("composite");
    expect(
      resolveCreateBackendChoice("local_shell", ["named:assets"], {
        backendsLoading: false,
        userTouched: false,
      }),
    ).toBe("named:assets");
    expect(
      resolveCreateBackendChoice("composite", ["named:assets"], {
        backendsLoading: false,
        userTouched: false,
      }),
    ).toBe("named:assets");
  });

  it("leaves composite in place once the user has chosen it", () => {
    expect(
      resolveCreateBackendChoice("composite", ["named:assets"], {
        backendsLoading: false,
        userTouched: true,
      }),
    ).toBeNull();
    expect(
      resolveCreateBackendChoice(
        "named:assets",
        ["named:assets", "named:logs"],
        {
          backendsLoading: false,
          userTouched: true,
        },
      ),
    ).toBeNull();
  });

  it("points the composite default at an allowed backend", () => {
    expect(
      resolveRestrictedCompositeDefault("local_shell", ["named:assets"], false),
    ).toBe("named:assets");
    expect(
      resolveRestrictedCompositeDefault(
        "named:assets",
        ["named:assets"],
        false,
      ),
    ).toBeNull();
    expect(
      resolveRestrictedCompositeDefault("local_shell", [], true),
    ).toBeNull();
    expect(
      resolveRestrictedCompositeDefault("local_shell", [], false),
    ).toBeUndefined();
  });
});
