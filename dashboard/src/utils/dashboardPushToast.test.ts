import { beforeEach, describe, expect, it } from "vitest";
import {
  claimPushLock,
  claimSystemPush,
  markPushHandled,
  parseDashboardPushFrame,
  PUSH_HANDLED_TTL_MS,
  readSystemNotifyPermission,
  resolvePushDelivery,
  systemNotificationTag,
  truncatePushText,
  wasPushHandled,
} from "./dashboardPushToast";

describe("parseDashboardPushFrame", () => {
  it("accepts a dashboard_push frame", () => {
    expect(
      parseDashboardPushFrame({
        type: "dashboard_push",
        agent_id: "a1",
        thread_id: "thr_1",
        text: "记得喝水",
        agent_name: "助手",
      }),
    ).toEqual({
      type: "dashboard_push",
      agent_id: "a1",
      thread_id: "thr_1",
      text: "记得喝水",
      agent_name: "助手",
    });
  });

  it("rejects other frame types and incomplete payloads", () => {
    expect(
      parseDashboardPushFrame({ type: "token", content: "hi" }),
    ).toBeNull();
    expect(
      parseDashboardPushFrame({
        type: "dashboard_push",
        agent_id: "a1",
        text: "x",
      }),
    ).toBeNull();
    expect(parseDashboardPushFrame(null)).toBeNull();
  });
});

describe("truncatePushText", () => {
  it("keeps short text intact", () => {
    expect(truncatePushText("记得喝水")).toBe("记得喝水");
  });

  it("truncates long text with an ellipsis", () => {
    const long = "a".repeat(300);
    const out = truncatePushText(long, 80);
    expect(out.length).toBe(81);
    expect(out.endsWith("…")).toBe(true);
  });
});

describe("resolvePushDelivery", () => {
  it("adds a system notification when granted and the page is hidden", () => {
    expect(
      resolvePushDelivery({ permission: "granted", visible: false }),
    ).toEqual({ system: true, offerEnable: false });
    expect(
      resolvePushDelivery({ permission: "granted", visible: true }),
    ).toEqual({ system: false, offerEnable: false });
  });

  it("offers the enable action only while permission is still undecided", () => {
    expect(
      resolvePushDelivery({ permission: "default", visible: true }),
    ).toEqual({ system: false, offerEnable: true });
    expect(
      resolvePushDelivery({ permission: "default", visible: false }),
    ).toEqual({ system: false, offerEnable: true });
    expect(
      resolvePushDelivery({ permission: "denied", visible: true }),
    ).toEqual({ system: false, offerEnable: false });
    expect(
      resolvePushDelivery({ permission: "unsupported", visible: false }),
    ).toEqual({ system: false, offerEnable: false });
  });
});

describe("readSystemNotifyPermission", () => {
  it("treats an insecure or missing Notification API as unsupported", () => {
    expect(readSystemNotifyPermission(false, { permission: "granted" })).toBe(
      "unsupported",
    );
    expect(readSystemNotifyPermission(true, undefined)).toBe("unsupported");
  });

  it("passes through the browser permission", () => {
    expect(readSystemNotifyPermission(true, { permission: "default" })).toBe(
      "default",
    );
    expect(readSystemNotifyPermission(true, { permission: "granted" })).toBe(
      "granted",
    );
    expect(readSystemNotifyPermission(true, { permission: "denied" })).toBe(
      "denied",
    );
  });
});

describe("system notification dedupe", () => {
  const key = "thr_1\n记得喝水";

  beforeEach(() => {
    localStorage.clear();
  });

  it("tags a thread so a later push replaces the previous notice", () => {
    expect(systemNotificationTag("thr_1")).toBe("dash-push:thr_1");
  });

  it("lets a visible tab suppress background copies of the same push", () => {
    markPushHandled(localStorage, key, 1_000);
    expect(wasPushHandled(localStorage, key, 1_500)).toBe(true);
    expect(wasPushHandled(localStorage, key, 1_000 + PUSH_HANDLED_TTL_MS)).toBe(
      false,
    );
  });

  it("gives the system notification to one tab", () => {
    expect(claimPushLock(localStorage, key, "tab-a", 1_000)).toBe(true);
    expect(claimPushLock(localStorage, key, "tab-b", 1_100)).toBe(false);
  });

  it("claims synchronously and lets a visible tab suppress the rest", () => {
    expect(claimSystemPush(localStorage, key, "tab-a", 1_000)).toBe(true);
    expect(claimSystemPush(localStorage, key, "tab-b", 1_100)).toBe(false);
    localStorage.clear();
    markPushHandled(localStorage, key, 2_000);
    expect(claimSystemPush(localStorage, key, "tab-a", 2_100)).toBe(false);
  });
});
