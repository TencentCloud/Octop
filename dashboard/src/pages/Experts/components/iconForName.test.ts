import { describe, expect, it } from "vitest";
import {
  normalizeAgentScopedApiUrl,
  resolveExpertAvatarUrl,
} from "./iconForName";

describe("normalizeAgentScopedApiUrl", () => {
  it("encodes bridge shadow agent ids the same way as chat WS paths", () => {
    const id = "bridge:01CID:01REMOTE";
    expect(normalizeAgentScopedApiUrl(`/api/agents/${id}/avatar`)).toBe(
      `/api/agents/${encodeURIComponent(id)}/avatar`,
    );
  });

  it("does not double-encode an already percent-encoded agent id", () => {
    const id = "bridge:01CID:01REMOTE";
    const encoded = `/api/agents/${encodeURIComponent(id)}/avatar`;
    expect(normalizeAgentScopedApiUrl(encoded)).toBe(encoded);
  });

  it("preserves query strings on avatar URLs", () => {
    const id = "bridge:01CID:01REMOTE";
    expect(normalizeAgentScopedApiUrl(`/api/agents/${id}/avatar?v=3`)).toBe(
      `/api/agents/${encodeURIComponent(id)}/avatar?v=3`,
    );
  });

  it("leaves non-agent paths unchanged", () => {
    expect(normalizeAgentScopedApiUrl("/experts/avatars/scene-tech.svg")).toBe(
      "/experts/avatars/scene-tech.svg",
    );
  });
});

describe("resolveExpertAvatarUrl", () => {
  it("normalizes bridge avatar API paths", () => {
    const id = "bridge:01CID:01REMOTE";
    expect(resolveExpertAvatarUrl(`/api/agents/${id}/avatar`)).toBe(
      `/api/agents/${encodeURIComponent(id)}/avatar`,
    );
  });

  it("returns null for empty input", () => {
    expect(resolveExpertAvatarUrl(null)).toBeNull();
    expect(resolveExpertAvatarUrl("  ")).toBeNull();
  });
});
