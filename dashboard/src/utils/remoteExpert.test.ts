import { describe, expect, it } from "vitest";
import {
  groupExpertsByConnection,
  expertDeleteConfirm,
  isBridgeAgentId,
  isRemoteShadowAgent,
  rewritePeerSpeakerId,
  toBridgeShadowAgentId,
  isRemotePeerOnly,
  remoteSurfaceMode,
  retainDisconnectedBridgeAgents,
} from "./remoteExpert";

describe("isBridgeAgentId", () => {
  it("matches the shadow id prefix", () => {
    expect(isBridgeAgentId("bridge:abc:aid")).toBe(true);
    expect(isBridgeAgentId("01LOCAL")).toBe(false);
    expect(isBridgeAgentId(null)).toBe(false);
  });
});

describe("isRemoteShadowAgent", () => {
  it("treats bridge rows and shadow ids as remote", () => {
    expect(isRemoteShadowAgent({ agent_id: "01LOCAL", bridge: true })).toBe(
      true,
    );
    expect(isRemoteShadowAgent({ agent_id: "bridge:cid:aid" })).toBe(true);
    expect(isRemoteShadowAgent({ agent_id: "01LOCAL" })).toBe(false);
  });
});

describe("expertDeleteConfirm", () => {
  const t = (key: string, options?: Record<string, string>) =>
    `${key}:${options?.name ?? ""}:${options?.connection ?? ""}`;

  it("uses the local copy for a local expert", () => {
    expect(
      expertDeleteConfirm({ name: "本地", agent_id: "01LOCAL" }, t),
    ).toEqual({
      title: "experts.confirmDelete:本地:",
      description: "experts.confirmDeleteHint::",
    });
  });

  it("names the peer connection when deleting a shadow", () => {
    const copy = expertDeleteConfirm(
      {
        name: "云端",
        agent_id: "bridge:cid:aid",
        bridge_connection_name: "公司云端",
      },
      t,
    );
    expect(copy.title).toBe("experts.confirmDeleteRemote:云端:");
    expect(copy.description).toContain("experts.confirmDeleteRemoteWhere:");
    expect(copy.description).toContain("公司云端");
  });
});

describe("rewritePeerSpeakerId", () => {
  it("maps peer-local speakers onto the room shadow id", () => {
    expect(toBridgeShadowAgentId("cid", "doctor")).toBe("bridge:cid:doctor");
    expect(rewritePeerSpeakerId("bridge:cid:team", "doctor")).toBe(
      "bridge:cid:doctor",
    );
    expect(rewritePeerSpeakerId("bridge:cid:team", "team")).toBe(
      "bridge:cid:team",
    );
    expect(rewritePeerSpeakerId("local-host", "doctor")).toBe("doctor");
  });
});

describe("remoteSurfaceMode", () => {
  it("marks host-only settings as peer-only", () => {
    expect(remoteSurfaceMode("chat")).toBe("ok");
    expect(remoteSurfaceMode("tasks")).toBe("ok");
    expect(isRemotePeerOnly("skillPackages")).toBe(true);
    expect(isRemotePeerOnly("acpGlobal")).toBe(true);
    expect(isRemotePeerOnly("browserHost")).toBe(true);
    expect(isRemotePeerOnly("connectorsManage")).toBe(true);
    expect(isRemotePeerOnly("knowledgeManage")).toBe(true);
  });
});

describe("groupExpertsByConnection", () => {
  it("puts local experts first, then one group per connection", () => {
    const groups = groupExpertsByConnection(
      [
        {
          agent_id: "L1",
          bridge: false,
        },
        {
          agent_id: "bridge:c1:a1",
          bridge: true,
          bridge_connection_id: "c1",
          bridge_connection_name: "Lab",
        },
        {
          agent_id: "bridge:c1:a2",
          bridge: true,
          bridge_connection_id: "c1",
          bridge_connection_name: "Lab",
        },
        {
          agent_id: "bridge:c2:a1",
          bridge: true,
          bridge_connection_id: "c2",
          bridge_connection_name: "Office",
          bridge_disconnected: true,
        },
      ],
      "本机",
    );
    expect(groups.map((g) => g.key)).toEqual(["local", "c1", "c2"]);
    expect(groups[0]?.label).toBe("本机");
    expect(groups[1]?.agents.map((a) => a.agent_id)).toEqual([
      "bridge:c1:a1",
      "bridge:c1:a2",
    ]);
    expect(groups[2]?.disconnected).toBe(true);
  });
});

describe("retainDisconnectedBridgeAgents", () => {
  it("keeps previous remotes when the live connection dropped", () => {
    const prev = [
      {
        agent_id: "L1",
        state: "running",
        bridge: false,
      },
      {
        agent_id: "bridge:c1:a1",
        state: "running",
        bridge: true,
        bridge_connection_id: "c1",
      },
    ];
    const next = [{ agent_id: "L1", state: "running", bridge: false }];
    const merged = retainDisconnectedBridgeAgents(prev, next, new Set(["c1"]));
    expect(merged.map((a) => a.agent_id)).toEqual(["L1", "bridge:c1:a1"]);
    expect(merged[1]?.bridge_disconnected).toBe(true);
    expect(merged[1]?.state).toBe("stopped");
  });

  it("drops remotes whose connection was deleted", () => {
    const prev = [
      {
        agent_id: "bridge:c1:a1",
        state: "running",
        bridge: true,
        bridge_connection_id: "c1",
      },
    ];
    const merged = retainDisconnectedBridgeAgents(prev, [], new Set());
    expect(merged).toEqual([]);
  });

  it("does not keep stale remotes once the connection is live again", () => {
    const prev = [
      {
        agent_id: "bridge:c1:old",
        state: "stopped",
        bridge: true,
        bridge_connection_id: "c1",
        bridge_disconnected: true,
      },
    ];
    const next = [
      {
        agent_id: "bridge:c1:new",
        state: "running",
        bridge: true,
        bridge_connection_id: "c1",
      },
    ];
    const merged = retainDisconnectedBridgeAgents(prev, next, new Set(["c1"]));
    expect(merged.map((a) => a.agent_id)).toEqual(["bridge:c1:new"]);
    expect(merged[0]?.bridge_disconnected).toBe(false);
  });
});
