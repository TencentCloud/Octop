import { describe, expect, it } from "vitest";

import type { BridgeConnection } from "../../../api/modules/bridge";
import {
  inboundPeerAddress,
  inboundSourceIp,
  peerHostLabel,
} from "./bridgePeerLabel";

function row(partial: Partial<BridgeConnection>): BridgeConnection {
  return {
    connection_id: "cid",
    peer_base_url: "http://127.0.0.1:8088",
    peer_username: "alice",
    display_name: "203.0.113.8",
    notes: null,
    status: "connected",
    last_error: null,
    last_seen_at: null,
    auto_reconnect: false,
    created_at: 1,
    updated_at: 1,
    has_password: false,
    inbound: true,
    ...partial,
  };
}

describe("inbound peer labels", () => {
  it("shows the observed IP when the advertised URL is loopback", () => {
    const connection = row({ peer_client_host: "203.0.113.8" });
    expect(inboundPeerAddress(connection)).toBe("203.0.113.8");
    expect(inboundSourceIp(connection)).toBe("");
  });

  it("keeps a public advertise URL and adds the source IP", () => {
    const connection = row({
      peer_base_url: "https://office.example",
      peer_client_host: "203.0.113.8",
    });
    expect(inboundPeerAddress(connection)).toBe("https://office.example");
    expect(inboundSourceIp(connection)).toBe("203.0.113.8");
  });
});

describe("peerHostLabel", () => {
  it("keeps the hostname and a non-default port", () => {
    expect(peerHostLabel("https://demo.octop.chat/path")).toBe(
      "demo.octop.chat",
    );
    expect(peerHostLabel("http://sandbox-a156c721:8088")).toBe(
      "sandbox-a156c721:8088",
    );
  });

  it("leaves a bare address unchanged", () => {
    expect(peerHostLabel("203.0.113.8")).toBe("203.0.113.8");
    expect(peerHostLabel("")).toBe("");
  });
});
