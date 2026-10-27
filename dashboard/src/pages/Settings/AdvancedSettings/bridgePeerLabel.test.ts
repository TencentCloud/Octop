import { describe, expect, it } from "vitest";

import type { BridgeConnection } from "../../../api/modules/bridge";
import {
  inboundPeerAddress,
  inboundSourceIp,
  maskPeerAccount,
  maskPeerAddress,
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

describe("maskPeerAddress", () => {
  it("keeps the scheme and port, masking the host ends", () => {
    expect(maskPeerAddress("https://cloud.corp.example.com")).toBe(
      "https://cl••••••om",
    );
    expect(maskPeerAddress("http://sandbox-a156c721:8088")).toBe(
      "http://sa••••••21:8088",
    );
  });

  it("masks the middle two octets of an IPv4 address", () => {
    expect(maskPeerAddress("203.0.113.8")).toBe("203.•••.•••.8");
    expect(maskPeerAddress("10.0.0.1")).toBe("10.•••.•••.1");
  });

  it("drops the default port and keeps a bare host masked", () => {
    expect(maskPeerAddress("demo.octop.chat")).toBe("de••••••at");
  });

  it("degrades short values to their first character", () => {
    expect(maskPeerAddress("ab")).toBe("a••");
    expect(maskPeerAddress("a")).toBe("•");
    expect(maskPeerAddress("")).toBe("");
  });
});

describe("maskPeerAccount", () => {
  it("keeps the first and last two characters", () => {
    expect(maskPeerAccount("administrator")).toBe("ad••••••or");
  });

  it("keeps only the first character for short accounts", () => {
    expect(maskPeerAccount("alice")).toBe("a••");
    expect(maskPeerAccount("bob")).toBe("b••");
    expect(maskPeerAccount("a")).toBe("•");
  });

  it("counts characters, not code units", () => {
    expect(maskPeerAccount("李雷")).toBe("李••");
  });

  it("leaves an empty account empty", () => {
    expect(maskPeerAccount("")).toBe("");
  });
});
