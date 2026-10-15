import { describe, expect, it } from "vitest";
import type { OctopAgent } from "./AgentContext";
import {
  agentsSnapshotEqual,
  mapBridgeAgent,
  projectChatAgentOption,
  selectEnabledExperts,
} from "./AgentContext";

function agent(
  agent_id: string,
  state: OctopAgent["state"],
  overrides: Partial<OctopAgent> = {},
): OctopAgent {
  return {
    id: 0,
    agent_id,
    name: agent_id,
    description: null,
    persona_mbti: null,
    default_model: null,
    system_prompt: null,
    template_name: null,
    state,
    last_error: null,
    icon: null,
    icon_name: null,
    icon_url: null,
    color: null,
    config: {},
    ...overrides,
  };
}

describe("selectEnabledExperts", () => {
  it("keeps only running experts when no resolved id is provided", () => {
    const agents = [
      agent("A", "running"),
      agent("B", "stopped"),
      agent("C", "starting"),
      agent("D", "failed"),
      agent("E", "stopping"),
    ];
    expect(selectEnabledExperts(agents, null).map((a) => a.agent_id)).toEqual([
      "A",
    ]);
  });

  it("hides general-assistant and system-doctor style experts once they are stopped", () => {
    // User's two scenarios from the bug report.
    const agents = [
      agent("G1", "stopped", { template_name: "general-assistant" }),
      agent("G2", "running", { template_name: "general-assistant" }),
      agent("S1", "stopped", { template_name: "cvm-ai-doctor" }),
      agent("S2", "running", { template_name: "cvm-ai-doctor" }),
    ];
    const result = selectEnabledExperts(agents, null).map((a) => a.agent_id);
    // Both templates follow the same rule: only running ones survive.
    expect(result).toEqual(["G2", "S2"]);
  });

  it("hides the focused expert once it is stopped (no pinning)", () => {
    // Regression for: stopping the focused expert in the chat page used to
    // leave it pinned in the sidebar because of an early pinActive default.
    const agents = [
      agent("S1", "stopped", { template_name: "cvm-ai-doctor" }),
      agent("G1", "running", { template_name: "general-assistant" }),
    ];
    // S1 is the resolvedAgentId (URL is /chat/S1). Without pinActive it must
    // disappear from the sidebar just like every other stopped expert.
    const sidebar = selectEnabledExperts(agents, "S1").map((a) => a.agent_id);
    expect(sidebar).toEqual(["G1"]);
    // @-picker / minimal-layout path also excludes it.
    const pickable = selectEnabledExperts(agents, "S1", {
      pinActive: false,
    }).map((a) => a.agent_id);
    expect(pickable).toEqual(["G1"]);
  });

  it("is a no-op when every expert is running", () => {
    const agents = [agent("A", "running"), agent("B", "running")];
    expect(selectEnabledExperts(agents, null)).toEqual(agents);
  });

  it("returns empty when nothing is running and there is no active pin", () => {
    const agents = [agent("A", "stopped"), agent("B", "failed")];
    expect(selectEnabledExperts(agents, null)).toEqual([]);
  });

  it("opt-in pinActive=true still keeps the active stopped expert (API stability)", () => {
    // Pinning is no longer the default — every production caller passes
    // pinActive:false — but the option still exists in case a future
    // surface wants to keep the focused expert visible.
    const agents = [
      agent("S1", "stopped", { template_name: "cvm-ai-doctor" }),
      agent("G1", "running", { template_name: "general-assistant" }),
    ];
    const result = selectEnabledExperts(agents, "S1", { pinActive: true }).map(
      (a) => a.agent_id,
    );
    expect(result).toEqual(["S1", "G1"]);
  });
});

describe("projectChatAgentOption", () => {
  it("projects the full OctopAgent down to ChatAgentOption shape", () => {
    const projected = projectChatAgentOption(
      agent("S1", "running", {
        icon_name: "cpu",
        icon_url: "https://example/icon.png",
        color: "#0052D9",
        is_shared: 1,
        is_owner: 0,
        owner_username: "alice",
        bridge: true,
        bridge_connection_name: "lab",
      }),
    );
    expect(projected).toEqual({
      agent_id: "S1",
      name: "S1",
      icon_name: "cpu",
      icon_url: "https://example/icon.png",
      color: "#0052D9",
      is_shared: true,
      is_owner: false,
      owner_username: "alice",
      bridge: true,
      bridge_connection_id: null,
      bridge_connection_name: "lab",
      bridge_connection_icon: null,
      bridge_disconnected: false,
      bridge_inbound: false,
    });
  });

  it("normalizes undefined owner_username to null", () => {
    const projected = projectChatAgentOption(agent("X", "running"));
    expect(projected.owner_username).toBeNull();
    expect(projected.is_shared).toBe(false);
    expect(projected.is_owner).toBe(false);
    expect(projected.bridge).toBe(false);
    expect(projected.bridge_connection_id).toBeNull();
    expect(projected.bridge_connection_name).toBeNull();
    expect(projected.bridge_connection_icon).toBeNull();
    expect(projected.bridge_disconnected).toBe(false);
    expect(projected.bridge_inbound).toBe(false);
  });

  it("keeps a disconnected remote expert in the enabled list", () => {
    const agents = [
      agent("bridge:cid:aid", "stopped", {
        bridge: true,
        bridge_disconnected: true,
      }),
      agent("L1", "running"),
    ];
    expect(selectEnabledExperts(agents, null).map((a) => a.agent_id)).toEqual([
      "bridge:cid:aid",
      "L1",
    ]);
  });
});

describe("mapBridgeAgent", () => {
  const conn = {
    connection_id: "cid",
    display_name: "Lab",
    icon_name: "cloud",
    inbound: false,
    has_password: true,
  };

  it("keeps the peer expert's model, connectors, knowledge bases, and mode", () => {
    const mapped = mapBridgeAgent(
      {
        agent_id: "bridge:cid:01AGENT",
        name: "Peer",
        kind: "expert",
        default_model: " prov/peer-model ",
        knowledge_base_ids: ["kb1", "  ", 3],
        mcp_servers: ["mail"],
        config: { conversation_mode: "plan", sandbox: "drop-me" },
      },
      conn,
    );
    expect(mapped.default_model).toBe("prov/peer-model");
    expect(mapped.knowledge_base_ids).toEqual(["kb1"]);
    expect(mapped.mcp_servers).toEqual(["mail"]);
    expect(mapped.config).toEqual({ conversation_mode: "plan" });
  });

  it("drops connectors on a peer team and ignores a missing composer payload", () => {
    const team = mapBridgeAgent(
      {
        agent_id: "bridge:cid:team",
        kind: "team",
        mcp_servers: ["mail"],
        knowledge_base_ids: ["kb1"],
      },
      conn,
    );
    expect(team.mcp_servers).toEqual([]);
    expect(team.knowledge_base_ids).toEqual(["kb1"]);
    expect(team.default_model).toBeNull();

    const bare = mapBridgeAgent({ agent_id: "bridge:cid:bare" }, conn);
    expect(bare.default_model).toBeNull();
    expect(bare.knowledge_base_ids).toBeUndefined();
    expect(bare.mcp_servers).toBeUndefined();
    expect(bare.config).toEqual({});
  });
});

describe("agentsSnapshotEqual", () => {
  it("notices expert default model, knowledge bases, and connectors", () => {
    const base = [
      agent("A", "running", {
        default_model: null,
        knowledge_base_ids: [],
        mcp_servers: [],
      }),
    ];
    expect(agentsSnapshotEqual(base, base)).toBe(true);
    expect(
      agentsSnapshotEqual(base, [
        agent("A", "running", {
          default_model: "prov/model",
          knowledge_base_ids: [],
          mcp_servers: [],
        }),
      ]),
    ).toBe(false);
    expect(
      agentsSnapshotEqual(base, [
        agent("A", "running", {
          default_model: null,
          knowledge_base_ids: ["kb1"],
          mcp_servers: [],
        }),
      ]),
    ).toBe(false);
    expect(
      agentsSnapshotEqual(base, [
        agent("A", "running", {
          default_model: null,
          knowledge_base_ids: [],
          mcp_servers: ["mail"],
        }),
      ]),
    ).toBe(false);
  });
});
