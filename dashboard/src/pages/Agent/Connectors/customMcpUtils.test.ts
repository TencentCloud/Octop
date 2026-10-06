import { describe, expect, it } from "vitest";

import { cardsToServers, newCard, serversToCards } from "./customMcpUtils";

describe("custom MCP certificate configuration", () => {
  it("retains uploaded certificates through JSON and visual editing", () => {
    const servers = {
      private: {
        transport: "streamable_http" as const,
        url: "https://mcp.example.com/mcp",
        ca_cert: "PEM certificate",
        ca_cert_name: "ca.pem",
      },
    };
    const cards = serversToCards(servers);
    expect(cards[0].useCustomCertificate).toBe(true);
    expect(cardsToServers(cards).private).toMatchObject(servers.private);
  });

  it("leaves normal HTTPS unchanged and drops custom trust when unchecked", () => {
    const card = {
      ...newCard("streamable_http", 0),
      url: "https://mcp.example.com/mcp",
      caCert: "old certificate",
      caCertName: "old.pem",
    };
    expect(cardsToServers([card])[card.name]).not.toHaveProperty("ca_cert");
    expect(cardsToServers([card])[card.name]).not.toHaveProperty(
      "ca_cert_name",
    );
  });

  it("requires an HTTPS URL and certificate when the option is selected", () => {
    const card = {
      ...newCard("streamable_http", 0),
      url: "https://mcp.example.com/mcp",
      useCustomCertificate: true,
    };
    expect(() => cardsToServers([card])).toThrow("certificate_required");
    expect(() =>
      cardsToServers([{ ...card, url: "http://127.0.0.1/mcp", caCert: "PEM" }]),
    ).toThrow("certificate_required");
  });

  it("does not carry HTTPS certificates into stdio configuration", () => {
    const card = {
      ...newCard("stdio", 0),
      command: "test-server",
      useCustomCertificate: true,
      caCert: "PEM",
    };
    expect(cardsToServers([card])[card.name]).not.toHaveProperty("ca_cert");
  });
});
