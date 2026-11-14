import { describe, expect, it } from "vitest";

import {
  cardsToServers,
  mergeCustomMcpCards,
  newCard,
  serversToCards,
} from "./customMcpUtils";

describe("custom MCP OAuth app credentials", () => {
  it("leaves oauth_client out when nothing is filled in", () => {
    const card = {
      ...newCard("streamable_http", 0),
      url: "https://a.test/mcp",
    };
    expect(cardsToServers([card])[card.name].oauth_client).toBeUndefined();
  });

  it("sends the typed client, trimmed, with only the fields that are set", () => {
    const card = {
      ...newCard("streamable_http", 0),
      url: "https://a.test/mcp",
      oauthClientId: " cid ",
      oauthClientSecret: "shh",
      oauthScope: " repo ",
    };
    expect(cardsToServers([card])[card.name].oauth_client).toEqual({
      client_id: "cid",
      client_secret: "shh",
      scope: "repo",
    });
  });

  it("omits the secret for a saved client so the server keeps it", () => {
    const [card] = serversToCards({
      srv: {
        transport: "streamable_http",
        url: "https://a.test/mcp",
        oauth_client: {
          client_id: "cid",
          has_client_secret: true,
          token_endpoint: "https://auth.a.test/token",
          authorization_endpoint: "https://auth.a.test/authorize",
        },
      },
    });
    expect(card.oauthClientSecretSaved).toBe(true);
    expect(card.oauthClientSecret).toBe("");
    expect(card.oauthClientOpen).toBe(true);
    expect(cardsToServers([card]).srv.oauth_client).toEqual({
      client_id: "cid",
      authorization_endpoint: "https://auth.a.test/authorize",
      token_endpoint: "https://auth.a.test/token",
    });
  });

  it("never attaches a client to a stdio server", () => {
    const card = {
      ...newCard("stdio", 0),
      command: "npx",
      oauthClientId: "cid",
    };
    expect(cardsToServers([card])[card.name].oauth_client).toBeUndefined();
  });

  it("keeps the credentials section open across a save", () => {
    const prev = [{ ...newCard("streamable_http", 0), oauthClientOpen: true }];
    const [merged] = mergeCustomMcpCards(
      {
        [prev[0].name]: { transport: "streamable_http", url: "https://a.test" },
      },
      prev,
    );
    expect(merged.oauthClientOpen).toBe(true);
  });
});
