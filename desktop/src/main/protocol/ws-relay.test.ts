import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import {
  createServer as createHttpServer,
  request as httpRequest,
  type IncomingMessage,
  type Server,
} from "node:http";
import type { Socket } from "node:net";
import { test } from "node:test";

import { WsRelay } from "./ws-relay";

/**
 * §5.2 — the relay is the only path a WebSocket can take out of the sandboxed
 * ``octop://app`` page. These cover what it refuses (wrong path, wrong origin,
 * sidecar down) and that a real handshake survives the rewrite, with bytes
 * flowing both ways afterwards.
 *
 * Everything here is hand-rolled over ``node:http``: the relay speaks the
 * handshake itself, so a WebSocket library would only hide the bytes that
 * matter.
 */

const ORIGIN = "octop://app";
const WS_KEY = randomBytes(16).toString("base64");

interface Seen {
  requestLine: string;
  headers: IncomingMessage["headers"];
}

function acceptFor(key: string): string {
  return createHash("sha1")
    .update(`${key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11`)
    .digest("base64");
}

/** A sidecar stand-in: completes the handshake, then echoes every byte. */
async function startUpstream(): Promise<{
  port: number;
  seen: Seen[];
  close: () => Promise<void>;
}> {
  const seen: Seen[] = [];
  // An upgraded socket leaves the server's own bookkeeping, so `close()` alone
  // would wait for a connection it no longer tracks.
  const sockets = new Set<Socket>();
  const server: Server = createHttpServer();
  server.on("connection", (socket: Socket) => {
    sockets.add(socket);
    socket.on("close", () => sockets.delete(socket));
  });
  server.on("upgrade", (req, socket) => {
    seen.push({ requestLine: `${req.method} ${req.url} HTTP/1.1`, headers: { ...req.headers } });
    const key = req.headers["sec-websocket-key"];
    if (typeof key !== "string") {
      socket.end("HTTP/1.1 400 Bad Request\r\nconnection: close\r\n\r\n");
      return;
    }
    socket.write(
      "HTTP/1.1 101 Switching Protocols\r\n" +
        "upgrade: websocket\r\n" +
        "connection: Upgrade\r\n" +
        `sec-websocket-accept: ${acceptFor(key)}\r\n\r\n`,
    );
    socket.on("data", (chunk) => socket.write(chunk));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", () => resolve()));
  const address = server.address();
  const port = typeof address === "object" && address ? address.port : 0;
  return {
    port,
    seen,
    close: async () => {
      for (const socket of sockets) socket.destroy();
      await new Promise<void>((resolve) => server.close(() => resolve()));
    },
  };
}

interface DialResult {
  status: number;
  socket: Socket | null;
  head: Buffer;
}

/** Minimal client: 101 arrives as ``upgrade``, anything else as ``response``. */
function dial(
  port: number,
  path: string,
  options: { origin?: string | null } = {},
): Promise<DialResult> {
  return new Promise((resolve, reject) => {
    const headers: Record<string, string> = {
      Connection: "Upgrade",
      Upgrade: "websocket",
      "Sec-WebSocket-Key": WS_KEY,
      "Sec-WebSocket-Version": "13",
    };
    if (options.origin !== null) headers.Origin = options.origin ?? ORIGIN;
    const req = httpRequest({ host: "127.0.0.1", port, path, headers });
    req.on("upgrade", (res, socket, head) => {
      socket.on("error", () => {});
      resolve({ status: res.statusCode ?? 0, socket, head });
    });
    req.on("response", (res) => {
      res.resume();
      res.on("end", () => resolve({ status: res.statusCode ?? 0, socket: null, head: Buffer.alloc(0) }));
    });
    req.on("error", reject);
    req.end();
  });
}

/** Resolve with the next chunk the socket delivers. */
function nextChunk(socket: Socket): Promise<string> {
  return new Promise((resolve) => {
    socket.once("data", (chunk: Buffer) => resolve(chunk.toString("utf8")));
  });
}

async function withRelay(
  options: { backendPort?: () => number; allowedOrigin?: string },
  body: (context: { relay: WsRelay; baseUrl: string; token: string; port: number }) => Promise<void>,
): Promise<void> {
  const relay = new WsRelay({
    backendPort: options.backendPort ?? (() => 0),
    allowedOrigin: options.allowedOrigin ?? ORIGIN,
  });
  const endpoint = await relay.start();
  const port = Number(new URL(endpoint.baseUrl).port);
  try {
    await body({ relay, baseUrl: endpoint.baseUrl, token: endpoint.token, port });
  } finally {
    await relay.stop();
  }
}

test("no endpoint until the relay is listening", async () => {
  const relay = new WsRelay({ backendPort: () => 0, allowedOrigin: ORIGIN });
  assert.equal(relay.endpoint, null);

  const endpoint = await relay.start();
  assert.ok(endpoint.baseUrl.startsWith("ws://127.0.0.1:"));
  // Long enough to be unguessable on the loopback port (§5.2).
  assert.ok(endpoint.token.length >= 16);

  await relay.stop();
  assert.equal(relay.endpoint, null);
});

test("a handshake reaches the sidecar with its path and query rewritten", async () => {
  const upstream = await startUpstream();
  try {
    await withRelay({ backendPort: () => upstream.port }, async ({ baseUrl, token, port }) => {
      const result = await dial(port, `/${token}/api/agents/a%2Fb/terminal/ws?session_id=s1`);
      assert.equal(result.status, 101);
      result.socket?.destroy();

      assert.equal(upstream.seen.length, 1);
      const seen = upstream.seen[0];
      assert.ok(seen, "the sidecar should have seen exactly one handshake");
      assert.equal(seen.requestLine, "GET /api/agents/a%2Fb/terminal/ws?session_id=s1 HTTP/1.1");
      // The sidecar must see itself, not the relay, or its own origin checks fail.
      assert.equal(seen.headers.host, `127.0.0.1:${upstream.port}`);
      assert.equal(seen.headers.origin, `http://127.0.0.1:${upstream.port}`);
      assert.equal(seen.headers["x-octop-proxy"], "1");
      assert.equal(seen.headers["sec-websocket-key"], WS_KEY);
      assert.equal(seen.headers["sec-websocket-version"], "13");
      assert.ok(baseUrl.startsWith("ws://127.0.0.1:"));
    });
  } finally {
    await upstream.close();
  }
});

test("bytes flow in both directions after the upgrade", async () => {
  const upstream = await startUpstream();
  try {
    await withRelay({ backendPort: () => upstream.port }, async ({ token, port }) => {
      const result = await dial(port, `/${token}/api/terminal/ws`);
      assert.equal(result.status, 101);
      const socket = result.socket!;

      socket.write("hello sidecar");
      assert.equal(await nextChunk(socket), "hello sidecar");

      socket.write("第二段");
      assert.equal(await nextChunk(socket), "第二段");

      socket.destroy();
    });
  } finally {
    await upstream.close();
  }
});

test("a wrong token is refused before the sidecar is contacted", async () => {
  const upstream = await startUpstream();
  try {
    await withRelay({ backendPort: () => upstream.port }, async ({ port }) => {
      const result = await dial(port, "/not-the-token/api/terminal/ws");
      assert.equal(result.status, 403);
      assert.equal(upstream.seen.length, 0);
    });
  } finally {
    await upstream.close();
  }
});

test("another origin cannot borrow the relay, even with the right path", async () => {
  const upstream = await startUpstream();
  try {
    await withRelay({ backendPort: () => upstream.port }, async ({ token, port }) => {
      const foreign = await dial(port, `/${token}/api/terminal/ws`, {
        origin: "https://evil.example",
      });
      assert.equal(foreign.status, 403);

      const absent = await dial(port, `/${token}/api/terminal/ws`, { origin: null });
      assert.equal(absent.status, 403);
      assert.equal(upstream.seen.length, 0);
    });
  } finally {
    await upstream.close();
  }
});

test("only /api paths are relayed", async () => {
  const upstream = await startUpstream();
  try {
    await withRelay({ backendPort: () => upstream.port }, async ({ token, port }) => {
      for (const suffix of ["/assets/index.js", "/", "/api-something"]) {
        const result = await dial(port, `/${token}${suffix}`);
        assert.equal(result.status, 403, `expected 403 for ${suffix}`);
      }
      assert.equal(upstream.seen.length, 0);
    });
  } finally {
    await upstream.close();
  }
});

test("a sidecar that is not up yet answers 503 instead of hanging", async () => {
  await withRelay({ backendPort: () => 0 }, async ({ token, port }) => {
    const result = await dial(port, `/${token}/api/terminal/ws`);
    assert.equal(result.status, 503);
  });
});

test("a refusal from the sidecar is passed back, not turned into a tunnel", async () => {
  // 404 before the upgrade: the relay must forward the answer and close.
  const server = createHttpServer();
  server.on("upgrade", (_req, socket) => {
    socket.end("HTTP/1.1 401 Unauthorized\r\ncontent-length: 0\r\nconnection: close\r\n\r\n");
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", () => resolve()));
  const address = server.address();
  const port = typeof address === "object" && address ? address.port : 0;

  try {
    await withRelay({ backendPort: () => port }, async ({ token, port: relayPort }) => {
      const result = await dial(relayPort, `/${token}/api/terminal/ws`);
      assert.equal(result.status, 401);
      assert.equal(result.socket, null);
    });
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

test("stop() refuses connections afterwards", async () => {
  const relay = new WsRelay({ backendPort: () => 1, allowedOrigin: ORIGIN });
  const endpoint = await relay.start();
  const port = Number(new URL(endpoint.baseUrl).port);
  await relay.stop();
  await assert.rejects(dial(port, `/${endpoint.token}/api/terminal/ws`), /ECONNREFUSED/);
});
