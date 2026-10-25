import { describe, expect, it } from "vitest";
import { matchesChatNavScope } from "./chatNavScope";

const localExpert = { agent_id: "e1", kind: "expert" };
const cloudExpert = { agent_id: "bridge:c1:e2", kind: "expert", bridge: true };
const localTeam = { agent_id: "t1", kind: "team" };
const cloudTeam = { agent_id: "bridge:c1:t2", kind: "team", bridge: true };

describe("matchesChatNavScope", () => {
  it("keeps cloud experts on the expert tab and cloud teams on the team tab", () => {
    expect(matchesChatNavScope(localExpert, "experts")).toBe(true);
    expect(matchesChatNavScope(cloudExpert, "experts")).toBe(true);
    expect(matchesChatNavScope(localTeam, "experts")).toBe(false);
    expect(matchesChatNavScope(cloudTeam, "experts")).toBe(false);

    expect(matchesChatNavScope(localTeam, "teams")).toBe(true);
    expect(matchesChatNavScope(cloudTeam, "teams")).toBe(true);
    expect(matchesChatNavScope(localExpert, "teams")).toBe(false);
    expect(matchesChatNavScope(cloudExpert, "teams")).toBe(false);
  });

  it("shows only remote experts and teams on the cloud tab", () => {
    expect(matchesChatNavScope(cloudExpert, "cloud")).toBe(true);
    expect(matchesChatNavScope(cloudTeam, "cloud")).toBe(true);
    expect(matchesChatNavScope(localExpert, "cloud")).toBe(false);
    expect(matchesChatNavScope(localTeam, "cloud")).toBe(false);
  });
});
