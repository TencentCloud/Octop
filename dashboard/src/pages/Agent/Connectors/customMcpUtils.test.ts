import { describe, expect, it } from "vitest";

import {
  applyServerJson,
  cardsToServers,
  mergeCustomMcpCards,
  newCard,
  serverJsonText,
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

  it("round-trips who can use the connector and its avatar icon", () => {
    const card = {
      ...newCard("streamable_http", 0),
      url: "https://a.test/mcp",
      visibility: "groups" as const,
      groupIds: ["g1"],
      avatarIcon: "plug",
    };
    const spec = cardsToServers([card])[card.name];
    expect(spec.visibility).toBe("groups");
    expect(spec.group_ids).toEqual(["g1"]);
    expect(spec.shared).toBe(true);
    expect(spec.avatar_icon).toBe("plug");
    const [back] = serversToCards({ [card.name]: spec });
    expect(back.visibility).toBe("groups");
    expect(back.groupIds).toEqual(["g1"]);
    expect(back.avatarIcon).toBe("plug");
  });

  it("round-trips one connector through the JSON editor", () => {
    const card = {
      ...newCard("streamable_http", 0),
      url: "https://a.test/mcp",
      displayName: "DeepWiki",
      avatarIcon: "plug",
      oauthConfigured: true,
      oauthClientId: "cid",
      oauthClientSecretSaved: true,
    };
    const text = serverJsonText(card);
    const back = applyServerJson(text, card, { nameLocked: true });
    expect(back.name).toBe(card.name);
    expect(back.displayName).toBe("DeepWiki");
    expect(back.url).toBe("https://a.test/mcp");
    expect(back.avatarIcon).toBe("plug");
    expect(back.oauthConfigured).toBe(true);
    expect(back.oauthClientSecretSaved).toBe(true);
    expect(back.key).toBe(card.key);
  });

  it("accepts a bare server spec and rejects a renamed saved id", () => {
    const card = {
      ...newCard("streamable_http", 0),
      url: "https://a.test/mcp",
    };
    const renamed = applyServerJson(
      JSON.stringify({
        url: "https://b.test/mcp",
        transport: "streamable_http",
      }),
      card,
    );
    expect(renamed.name).toBe(card.name);
    expect(renamed.url).toBe("https://b.test/mcp");
    expect(() =>
      applyServerJson(
        JSON.stringify({
          other: { url: "https://b.test/mcp", transport: "streamable_http" },
        }),
        card,
        { nameLocked: true },
      ),
    ).toThrow("name_locked");
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
