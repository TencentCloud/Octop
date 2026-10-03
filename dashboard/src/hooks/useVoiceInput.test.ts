import { afterEach, describe, expect, it, vi } from "vitest";
import { isMicrophoneBlockedByPolicy, isSttAvailable } from "./useVoiceInput";

const policyProperties = ["permissionsPolicy", "featurePolicy"] as const;
const originalPolicies = policyProperties.map((property) =>
  Object.getOwnPropertyDescriptor(document, property),
);

afterEach(() => {
  policyProperties.forEach((property, index) => {
    const original = originalPolicies[index];
    if (original) Object.defineProperty(document, property, original);
    else Reflect.deleteProperty(document, property);
  });
  vi.unstubAllGlobals();
});

describe("voice input permissions policy", () => {
  it.each(["permissionsPolicy", "featurePolicy"])(
    "disables voice input when %s denies the microphone",
    (property) => {
      vi.stubGlobal("webkitSpeechRecognition", vi.fn());
      const allowsFeature = vi.fn(() => false);
      Object.defineProperty(document, property, {
        configurable: true,
        value: { allowsFeature },
      });
      expect(isMicrophoneBlockedByPolicy()).toBe(true);
      expect(isSttAvailable()).toBe(false);
      expect(allowsFeature).toHaveBeenCalledWith("microphone");
    },
  );

  it("keeps voice input available when microphone use is allowed", () => {
    vi.stubGlobal("webkitSpeechRecognition", vi.fn());
    Object.defineProperty(document, "permissionsPolicy", {
      configurable: true,
      value: { allowsFeature: () => true },
    });
    expect(isSttAvailable()).toBe(true);
  });

  it("does not infer a denial when the policy API is unavailable", () => {
    vi.stubGlobal("webkitSpeechRecognition", vi.fn());
    expect(isMicrophoneBlockedByPolicy()).toBe(false);
    expect(isSttAvailable()).toBe(true);
  });
});
