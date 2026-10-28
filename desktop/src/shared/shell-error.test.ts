import assert from "node:assert/strict";
import { test } from "node:test";

import {
  decodeShellError,
  encodeShellError,
  FALLBACK_ERROR_MESSAGE,
  SHELL_ERROR_PARAM,
} from "./shell-error";

/**
 * The failure page is reached through a query string, so the payload has to come
 * back out byte-identical — CJK included — and every unusable input has to end on
 * a readable message rather than a blank page.
 */

test("a payload survives the URL round trip", () => {
  const decoded = decodeShellError(
    encodeShellError({
      title: "Octop 无法启动",
      message: "检测到本机运行时版本为 0.9.20，当前安装的是 0.9.31。",
      detail: "已安装版本: 0.9.31\n路径: /Users/me/.octop/portable",
      version: "0.9.31",
    }),
  );

  assert.equal(decoded.title, "Octop 无法启动");
  assert.equal(decoded.message, "检测到本机运行时版本为 0.9.20，当前安装的是 0.9.31。");
  assert.equal(decoded.detail, "已安装版本: 0.9.31\n路径: /Users/me/.octop/portable");
  assert.equal(decoded.version, "0.9.31");
});

test("the encoded payload is URL-safe", () => {
  // Characters that would otherwise change meaning inside a query string.
  const encoded = encodeShellError({ message: "a+b/c=d&e?f#g 中文" });
  assert.match(encoded, /^[A-Za-z0-9_-]+$/);
  assert.equal(decodeShellError(encoded).message, "a+b/c=d&e?f#g 中文");
});

test("a long detail is truncated so the URL stays sane", () => {
  const decoded = decodeShellError(encodeShellError({ message: "boom", detail: "x".repeat(6000) }));
  assert.ok(decoded.detail);
  assert.ok(decoded.detail.length < 4100, `detail was ${decoded.detail.length} chars`);
  assert.ok(decoded.detail.endsWith("…"));
});

test("missing or unusable payloads fall back to a readable message", () => {
  for (const input of [null, undefined, "", "not-base64!!", "eyJ9"]) {
    const decoded = decodeShellError(input);
    assert.equal(decoded.message, FALLBACK_ERROR_MESSAGE);
    assert.equal(decoded.detail, undefined);
  }
});

test("a payload without a message is not trusted", () => {
  const encoded = Buffer.from(JSON.stringify({ title: "x", detail: "y" }), "utf8").toString(
    "base64url",
  );
  assert.equal(decodeShellError(encoded).message, FALLBACK_ERROR_MESSAGE);
});

test("blank optional fields are dropped, not rendered as empty", () => {
  const decoded = decodeShellError(
    encodeShellError({ message: "boom", title: "   ", detail: "", version: "" }),
  );
  assert.equal(decoded.title, undefined);
  assert.equal(decoded.detail, undefined);
  assert.equal(decoded.version, undefined);
});

test("the query parameter name matches what the renderer reads", () => {
  assert.equal(SHELL_ERROR_PARAM, "payload");
});
