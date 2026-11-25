import { describe, expect, it } from "vitest";
import {
  matchesExpertLocation,
  matchesResourceAudience,
} from "./resourceAudience";

describe("matchesResourceAudience", () => {
  const mine = { owned: true, shared: false };
  const mineShared = { owned: true, shared: true };
  const incoming = { owned: false, shared: true };

  it("keeps every row on all", () => {
    expect(matchesResourceAudience("all", incoming)).toBe(true);
  });

  it("keeps owned rows on local, including ones I shared", () => {
    expect(matchesResourceAudience("local", mine)).toBe(true);
    expect(matchesResourceAudience("local", mineShared)).toBe(true);
    expect(matchesResourceAudience("local", incoming)).toBe(false);
  });

  it("keeps only incoming shares on shared", () => {
    expect(matchesResourceAudience("shared", mine)).toBe(false);
    expect(matchesResourceAudience("shared", mineShared)).toBe(false);
    expect(matchesResourceAudience("shared", incoming)).toBe(true);
  });
});

describe("matchesExpertLocation", () => {
  const local = { agent_id: "own", is_owner: true, is_shared: false };
  const sharedOut = { agent_id: "out", is_owner: true, is_shared: true };
  const sharedIn = { agent_id: "in", is_owner: false, is_shared: true };
  const cloud = { agent_id: "br:1:a", bridge: true, is_owner: true };

  it("shows incoming shares on all and shared, not on local", () => {
    expect(matchesExpertLocation(sharedIn, "all")).toBe(true);
    expect(matchesExpertLocation(sharedIn, "shared")).toBe(true);
    expect(matchesExpertLocation(sharedIn, "local")).toBe(false);
    expect(matchesExpertLocation(sharedIn, "cloud")).toBe(false);
  });

  it("keeps an expert I shared on local, not on shared", () => {
    expect(matchesExpertLocation(sharedOut, "local")).toBe(true);
    expect(matchesExpertLocation(sharedOut, "shared")).toBe(false);
    expect(matchesExpertLocation(sharedOut, "all")).toBe(true);
  });

  it("keeps cloud shadows on cloud and out of local", () => {
    expect(matchesExpertLocation(cloud, "cloud")).toBe(true);
    expect(matchesExpertLocation(cloud, "local")).toBe(false);
    expect(matchesExpertLocation(local, "cloud")).toBe(false);
  });
});
